"""Lag 8: executor-registry. Kun én executor pr. ``action.type``.

En executor kan kun kaldes med en billet, som gaten har udstedt til netop
denne handling (id + indholdshash), og hver billet kan bruges én gang. Et
direkte kald uden gyldig billet afvises. Det er forsvar i dybden inde i
processen; den egentlige grænse er, at kun ``intentd``'s gate holder
registret, og at ingen IPC-metode eksponerer executors.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from typing import Any, Callable

from app.gate.store import iso, utc_now


class DirectCallRejected(PermissionError):
    """An executor was called without a valid, unused gate ticket."""


class ExecutorUnavailable(RuntimeError):
    """The executor checked, before any side effect, that it cannot act now."""


@dataclass(frozen=True)
class GateTicket:
    action_id: str
    content_hash: str
    execution_id: str
    mac: str


@dataclass(frozen=True)
class ExecutorResult:
    """``status``: succeeded | partial | failed | unknown.

    ``state_transition`` is what the executor claims happened; the gate checks
    it against the transitions it allows for the action type.
    """

    status: str
    state_transition: tuple[str, str]
    result: dict[str, Any] = field(default_factory=dict)


class Executor:
    action_type: str = ""
    # Transitions this executor may report on success.
    success_transitions: frozenset[tuple[str, str]] = frozenset()

    def run(self, envelope: dict[str, Any], execution_id: str) -> ExecutorResult:  # pragma: no cover
        raise NotImplementedError

    def reconcile(self, action_id: str, execution_id: str) -> bool | None:
        """After a crash: did this execution take effect? ``True``/``False``
        only if the executor's durable state proves it; ``None`` = cannot tell."""
        return None

    def recorded_result(self, action_id: str) -> dict[str, Any]:
        return {"recovered": True}


class ExecutorRegistry:
    def __init__(self) -> None:
        self._executors: dict[str, Executor] = {}
        self._key = secrets.token_bytes(32)
        self._issued: set[str] = set()

    def register(self, executor: Executor) -> None:
        if not executor.action_type:
            raise ValueError("executor without action_type")
        if executor.action_type in self._executors:
            raise ValueError(f"executor for {executor.action_type} already registered")
        self._executors[executor.action_type] = executor

    def has(self, action_type: str) -> bool:
        return action_type in self._executors

    def executor(self, action_type: str) -> Executor:
        return self._executors[action_type]

    def _mac(self, action_id: str, content_hash: str, execution_id: str) -> str:
        msg = f"{action_id}\x00{content_hash}\x00{execution_id}".encode()
        return hmac.new(self._key, msg, hashlib.sha256).hexdigest()

    def issue(self, action_id: str, content_hash: str, execution_id: str) -> GateTicket:
        ticket = GateTicket(
            action_id, content_hash, execution_id, self._mac(action_id, content_hash, execution_id)
        )
        self._issued.add(ticket.mac)
        return ticket

    def reconcile(self, action_type: str, action_id: str, execution_id: str) -> bool | None:
        executor = self._executors.get(action_type)
        return executor.reconcile(action_id, execution_id) if executor else None

    def recorded_result(self, action_type: str, action_id: str) -> dict[str, Any]:
        return self._executors[action_type].recorded_result(action_id)

    def call(self, ticket: Any, envelope: dict[str, Any], content_hash: str) -> ExecutorResult:
        """The only way to run an executor."""
        if not isinstance(ticket, GateTicket):
            raise DirectCallRejected("no gate ticket")
        expected = self._mac(ticket.action_id, ticket.content_hash, ticket.execution_id)
        if not hmac.compare_digest(expected, ticket.mac) or ticket.mac not in self._issued:
            raise DirectCallRejected("ticket was not issued by this gate")
        if ticket.action_id != envelope.get("id") or ticket.content_hash != content_hash:
            raise DirectCallRejected("ticket does not match this action")
        self._issued.discard(ticket.mac)  # single use
        return self._executors[envelope["action"]["type"]].run(envelope, ticket.execution_id)


# --- Conversation executors -------------------------------------------------
#
# First flow (ADR-0001, "samtale om en sag"): the semantic event is written to
# the producer's durable outbox in the conversation log *before* any delivery
# (Phase 1 decision: outbox → publish → receiver acknowledges durable storage).
# The honest state after execution is therefore "recorded", never "delivered".

OUTBOX_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_outbox (
    event_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    envelope TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    delivery_state TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    acked_at TEXT
);
"""

# User-facing state of what was recorded (Architecture Baseline vocabulary):
# a proposal stays "proposed" until the recipient accepts.
VISIBLE_STATE = {
    "utterance": "recorded_not_delivered",
    "commitment_proposed": "proposed",
    "commitment_accepted": "accepted_recorded",
    "commitment_declined": "declined_recorded",
}


class ConversationOutboxExecutor(Executor):
    success_transitions = frozenset({("executing", "recorded")})

    def __init__(self, action_type: str, connect: Callable[[], sqlite3.Connection]) -> None:
        self.action_type = action_type
        self._connect = connect
        with closing(self._connect()) as conn:
            conn.executescript(OUTBOX_SCHEMA)

    def reconcile(self, action_id: str, execution_id: str) -> bool | None:
        # The outbox row is written in one transaction with the execution id,
        # so its presence proves the effect and its absence proves none.
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT execution_id FROM conversation_outbox WHERE event_id = ?", (action_id,)
            ).fetchone()
        if row is None:
            return False
        return row[0] == execution_id or None

    def recorded_result(self, action_id: str) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT conversation_id FROM conversation_outbox WHERE event_id = ?", (action_id,)
            ).fetchone()
        return {
            "conversation_id": row[0] if row else None,
            "visible_state": VISIBLE_STATE.get(self.action_type, "recorded_not_delivered"),
            "delivery": "pending",
            "recovered": True,
        }

    def run(self, envelope: dict[str, Any], execution_id: str) -> ExecutorResult:
        with closing(self._connect()) as conn:
            conn.execute(
                """INSERT INTO conversation_outbox (event_id, conversation_id, action_type, envelope,
                   execution_id, delivery_state, recorded_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
                (
                    envelope["id"],
                    envelope["conversation_id"],
                    self.action_type,
                    json.dumps(envelope, sort_keys=True, ensure_ascii=False),
                    execution_id,
                    iso(utc_now()),
                ),
            )
            conn.commit()
        return ExecutorResult(
            status="succeeded",
            state_transition=("executing", "recorded"),
            result={
                "conversation_id": envelope["conversation_id"],
                "visible_state": VISIBLE_STATE.get(self.action_type, "recorded_not_delivered"),
                "delivery": "pending",
            },
        )


# --- EiraSystemAPI executors (Gate 1.1) --------------------------------------
#
# EiraOS does not replace Ubuntu's services (Platform Principles): power goes
# to systemd-logind over the system D-Bus. The call is a fixed argv to
# busctl — no shell, no command assembled from input — and non-interactive,
# so logind's own polkit check decides. The package grants the eira service
# user exactly the login1 power actions (packaging/polkit/50-eira-power.rules).

Runner = Callable[[list[str]], tuple[int, str]]

LOGIN1 = ["org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager"]
POWER_METHODS = {
    "poweroff": ("CanPowerOff", "PowerOff"),
    "reboot": ("CanReboot", "Reboot"),
    "suspend": ("CanSuspend", "Suspend"),
}


def busctl_runner(argv: list[str]) -> tuple[int, str]:
    import subprocess

    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["/usr/bin/busctl", "--system", "--timeout=10", *argv],
        capture_output=True,
        text=True,
        timeout=15,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        check=False,
    )
    return completed.returncode, completed.stdout.strip()


class PowerExecutor(Executor):
    action_type = "system:power.request_action"
    success_transitions = frozenset({("executing", "requested")})

    def __init__(self, runner: Runner = busctl_runner) -> None:
        self._runner = runner

    def availability(self, action: str) -> str:
        """logind's answer: yes | challenge | no | na, or error."""
        can, _ = POWER_METHODS[action]
        try:
            code, out = self._runner(["call", *LOGIN1, can])
        except Exception:  # noqa: BLE001 - any failure means "cannot tell"
            return "error"
        if code != 0:
            return "error"
        # busctl prints: s "yes"
        answer = out.split(" ", 1)[1].strip('"') if out.startswith('s "') else "error"
        return answer if answer in {"yes", "challenge", "no", "na"} else "error"

    def run(self, envelope: dict[str, Any], execution_id: str) -> ExecutorResult:
        action = envelope["action"]["content"]["action"]
        answer = self.availability(action)
        if answer != "yes":
            # "challenge" would need interactive polkit auth, which a daemon
            # never triggers; anything else means logind refuses or is absent.
            raise ExecutorUnavailable(f"logind answers {answer!r} to {action}")
        _, method = POWER_METHODS[action]
        code, _ = self._runner(["call", *LOGIN1, method, "b", "false"])
        if code != 0:
            return ExecutorResult(
                "failed", ("executing", "failed"), {"operation": "power.request_action", "action": action}
            )
        # logind accepted the request; the machine now goes down. Honest
        # state: requested, not "done".
        return ExecutorResult(
            "succeeded",
            ("executing", "requested"),
            {"operation": "power.request_action", "action": action, "visible_state": "requested"},
        )


def default_registry(db_path: str) -> ExecutorRegistry:
    def connect() -> sqlite3.Connection:
        return sqlite3.connect(db_path, timeout=10)

    registry = ExecutorRegistry()
    for action_type in VISIBLE_STATE:
        registry.register(ConversationOutboxExecutor(action_type, connect))
    registry.register(PowerExecutor())
    return registry
