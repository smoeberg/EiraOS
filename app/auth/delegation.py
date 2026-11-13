"""På vegne af: a human lets the model *prepare* actions (bilag A pkt. 1).

A delegation never lets the model consent, confirm or execute; the gate keeps
those human-only. It only lets a model proposal through lag 4 for the actions
and targets the human chose.

Creating one is itself a decision and takes the trusted path (§ EIRA-
DELEGATION-1.0): ``propose`` returns the exact text the user will see, and
``activate`` needs a proof made with the session's consent key, which only the
desktop app's Rust core holds. Another program running as the same user, even
with the session id, cannot delegate. Revoking needs no proof: it only takes
power away.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel, ConfigDict, Field

from app.ipc.client import IpcClient

MAX_DELEGATION = timedelta(days=30)
# How long the user has between seeing the text and approving it.
PROPOSAL_TTL = timedelta(minutes=5)
NEVER_DELEGABLE = frozenset({"execute", "decide", "admin", "consent", "confirm"})


class DelegationScope(BaseModel):
    actions: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=lambda: ["*"])
    conditions: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(frozen=True, extra="forbid")


class DelegationCreateRequest(BaseModel):
    delegee_id: str
    scope: DelegationScope
    expires_in: timedelta = timedelta(hours=24)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DelegationRevokeRequest(BaseModel):
    delegation_id: str


class DelegationCheckRequest(BaseModel):
    delegee_id: str
    action: str
    target: str


@dataclass(frozen=True)
class Delegation:
    id: str
    delegator_id: str
    delegee_id: str
    scope: DelegationScope
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None
    metadata: dict[str, Any]

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > datetime.now(timezone.utc)

    def can_perform(self, action: str, target: str) -> bool:
        if not self.is_active:
            return False
        if "*" not in self.scope.actions and action not in self.scope.actions:
            return False
        if "*" not in self.scope.targets:
            if not any(
                target == pattern
                or (pattern.endswith("*") and target.startswith(pattern[:-1]))
                for pattern in self.scope.targets
            ):
                return False
        return _conditions_allow(self.scope.conditions, target)


def _conditions_allow(conditions: dict[str, Any], target: str) -> bool:
    if not conditions:
        return True
    allowed_targets = conditions.get("allowed_targets")
    if allowed_targets is not None:
        if not isinstance(allowed_targets, list) or target not in allowed_targets:
            return False
    return True


class DelegationRepository:
    """Stores delegations in the app database (``EIRA_APP_DB``), which the
    gate (intentd) and eira-delegationd share. ``db_path`` is for tests."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._db_path is None:
            from app import database

            path = database.DB_PATH
        else:
            path = self._db_path
        with closing(sqlite3.connect(path, timeout=5.0)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 5000")
            with conn:
                yield conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS delegation_proposals (
                    id TEXT PRIMARY KEY,
                    delegator_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    request TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    rendering_text TEXT NOT NULL,
                    rendering_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    used_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS delegations (
                    id TEXT PRIMARY KEY,
                    delegator_id TEXT NOT NULL,
                    delegee_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_delegations_active "
                "ON delegations(delegee_id, expires_at, revoked_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_delegations_delegator "
                "ON delegations(delegator_id)"
            )

    @staticmethod
    def _row(row: Any) -> Delegation:
        return Delegation(
            id=row["id"],
            delegator_id=row["delegator_id"],
            delegee_id=row["delegee_id"],
            scope=DelegationScope.model_validate_json(row["scope"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            revoked_at=datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None,
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def create(self, delegator_id: str, delegee_id: str, scope: DelegationScope,
               expires_at: datetime, metadata: dict[str, Any]) -> Delegation:
        self._ensure_schema()
        now = datetime.now(timezone.utc)
        delegation_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO delegations
                    (id, delegator_id, delegee_id, scope, expires_at, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (delegation_id, delegator_id, delegee_id, scope.model_dump_json(),
                 expires_at.isoformat(), now.isoformat(), json.dumps(metadata, sort_keys=True)),
            )
        return Delegation(delegation_id, delegator_id, delegee_id, scope,
                          expires_at, now, None, dict(metadata))

    def get_by_id(self, delegation_id: str) -> Delegation | None:
        self._ensure_schema()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM delegations WHERE id = ?", (delegation_id,)).fetchone()
        return self._row(row) if row else None

    def active_for_delegee(self, delegee_id: str) -> list[Delegation]:
        self._ensure_schema()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM delegations
                   WHERE delegee_id = ? AND revoked_at IS NULL AND expires_at > ?
                   ORDER BY expires_at""",
                (delegee_id, now),
            ).fetchall()
        return [self._row(row) for row in rows]

    def active_for_delegator(self, delegator_id: str) -> list[Delegation]:
        self._ensure_schema()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM delegations
                   WHERE delegator_id = ? AND revoked_at IS NULL AND expires_at > ?
                   ORDER BY expires_at""",
                (delegator_id, now),
            ).fetchall()
        return [self._row(row) for row in rows]

    def revoke(self, delegation_id: str) -> bool:
        self._ensure_schema()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE delegations SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (now, delegation_id),
            )
        return result.rowcount == 1

    def delete(self, delegation_id: str) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute("DELETE FROM delegations WHERE id = ?", (delegation_id,))


    # --- proposals (the trusted path) ---------------------------------------------

    def add_proposal(self, row: dict[str, Any]) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO delegation_proposals (id, delegator_id, session_id, request, content_hash,
                   rendering_text, rendering_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (row["id"], row["delegator_id"], row["session_id"], row["request"], row["content_hash"],
                 row["rendering_text"], row["rendering_hash"], row["created_at"]),
            )

    def proposal(self, proposal_id: str, delegator_id: str, session_id: str) -> dict[str, Any] | None:
        self._ensure_schema()
        not_before = (datetime.now(timezone.utc) - PROPOSAL_TTL).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM delegation_proposals WHERE id = ? AND delegator_id = ? AND session_id = ?
                   AND used_at IS NULL AND created_at > ?""",
                (proposal_id, delegator_id, session_id, not_before),
            ).fetchone()
        return dict(row) if row else None

    def claim_proposal(self, proposal_id: str, delegator_id: str, session_id: str,
                       content_hash: str, rendering_hash: str, not_before: datetime) -> dict[str, Any] | None:
        """Single use: the proposal is marked used in the same statement that
        finds it, so one proof cannot create two delegations."""
        self._ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                """UPDATE delegation_proposals SET used_at = ?
                    WHERE id = ? AND delegator_id = ? AND session_id = ? AND content_hash = ?
                      AND rendering_hash = ? AND used_at IS NULL AND created_at > ?
                RETURNING *""",
                (datetime.now(timezone.utc).isoformat(), proposal_id, delegator_id, session_id,
                 content_hash, rendering_hash, not_before.isoformat()),
            ).fetchone()
        return dict(row) if row else None


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


# What a target means, in the words the user approves. A target without an
# entry is shown as it is: never a friendlier guess at what it covers.
TARGET_WORDS = {
    "intent:system:power.request_action": "at slukke, genstarte eller sætte computeren i dvale",
    "intent:utterance": "at sende beskeder",
    "intent:commitment_proposed": "at foreslå aftaler",
    "intent:*": "alle slags handlinger",
}


def render(request: DelegationCreateRequest, expires_at: datetime) -> str:
    """The exact text the user approves (Danish, like the gate's renderer).
    It names the model's identity and every target, so the text says what the
    delegation covers and nothing else."""
    targets = sorted(request.scope.targets)
    what = " og ".join(TARGET_WORDS.get(t, t) for t in targets)
    raw = ", ".join(targets)
    until = expires_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"Eira ({request.delegee_id}) må forberede forslag om {what} ({raw}) "
        f"på dine vegne indtil {until}. Du skal stadig selv give samtykke til hvert forslag, "
        "før noget sker. Du kan trække tilladelsen tilbage når som helst."
    )


class DelegationService:
    def __init__(self, repo: DelegationRepository | None = None) -> None:
        self.repo = repo or DelegationRepository()

    @staticmethod
    def _validate(delegator_id: str, request: DelegationCreateRequest) -> None:
        if not delegator_id:
            raise PermissionError("delegator identity is required")
        if not request.delegee_id.startswith("model:"):
            raise PermissionError("only model delegatees are supported")
        if not request.scope.actions:
            raise ValueError("delegation must contain at least one action")
        if NEVER_DELEGABLE.intersection(request.scope.actions) or "*" in request.scope.actions:
            raise PermissionError("delegation can only grant prepare, never execute, decide or consent")
        if request.expires_in <= timedelta(0) or request.expires_in > MAX_DELEGATION:
            raise ValueError("delegation expiry must be > 0 and <= 30 days")

    def propose_delegation(self, delegator_id: str, session_id: str,
                           request: DelegationCreateRequest) -> dict[str, Any]:
        """Step 1 of the trusted path: validate and fix the text the user sees."""
        self._validate(delegator_id, request)
        now = datetime.now(timezone.utc)
        canonical = json.dumps(
            {"delegator_id": delegator_id, "request": request.model_dump(mode="json")},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        text = render(request, now + request.expires_in)
        proposal = {
            "id": "dlgp-" + uuid.uuid4().hex,
            "delegator_id": delegator_id,
            "session_id": session_id,
            "request": request.model_dump_json(),
            "content_hash": _sha256(canonical.encode()),
            "rendering_text": text,
            "rendering_hash": _sha256(text.encode()),
            "created_at": now.isoformat(),
        }
        self.repo.add_proposal(proposal)
        return {
            "proposal_id": proposal["id"],
            "content_hash": proposal["content_hash"],
            "rendering": {"text": text, "hash": proposal["rendering_hash"], "lang": "da"},
        }

    def activate(self, delegator_id: str, session_id: str, proposal_id: str,
                 content_hash: str, rendering_hash: str) -> Delegation:
        """Step 2: the caller has already verified the consent-key proof over
        exactly these values. Creates the delegation the user saw, once."""
        found = self.repo.claim_proposal(
            proposal_id, delegator_id, session_id, content_hash, rendering_hash,
            not_before=datetime.now(timezone.utc) - PROPOSAL_TTL,
        )
        if found is None:
            raise PermissionError("unknown, expired, used or changed delegation proposal")
        request = DelegationCreateRequest.model_validate_json(found["request"])
        delegation = self.create_delegation(delegator_id, request, metadata={"proposal_id": proposal_id})
        return delegation

    def create_delegation(self, delegator_id: str, request: DelegationCreateRequest,
                          metadata: dict[str, Any] | None = None) -> Delegation:
        """In-process only. Over IPC a delegation is created by ``activate``."""
        self._validate(delegator_id, request)
        delegation = self.repo.create(
            delegator_id, request.delegee_id, request.scope,
            datetime.now(timezone.utc) + request.expires_in, {**request.metadata, **(metadata or {})},
        )
        try:
            self._audit("delegation.created", delegator_id, {
                "delegation_id": delegation.id,
                "delegee_id": delegation.delegee_id,
                "scope": delegation.scope.model_dump(),
                "expires_at": delegation.expires_at.isoformat(),
            })
        except Exception:
            self.repo.delete(delegation.id)
            raise
        return delegation

    def revoke_delegation(self, request: DelegationRevokeRequest, revoked_by: str) -> bool:
        delegation = self.repo.get_by_id(request.delegation_id)
        if delegation is None:
            raise ValueError("delegation not found")
        if delegation.delegator_id != revoked_by:
            raise PermissionError("only the delegator can revoke this delegation")
        success = self.repo.revoke(request.delegation_id)
        if success:
            self._audit("delegation.revoked", revoked_by, {
                "delegation_id": delegation.id,
                "delegee_id": delegation.delegee_id,
            })
        return success

    def check_delegation(self, request: DelegationCheckRequest) -> bool:
        return any(
            delegation.can_perform(request.action, request.target)
            for delegation in self.repo.active_for_delegee(request.delegee_id)
        )

    def delegation_for(self, delegee_id: str, action: str, target: str,
                       delegator: str | None = None) -> Delegation | None:
        """The active delegation that lets ``delegee_id`` do ``action`` on
        ``target`` for ``delegator``. Another human's delegation never counts."""
        for delegation in self.repo.active_for_delegee(delegee_id):
            if delegator is not None and delegation.delegator_id != delegator:
                continue
            if delegation.can_perform(action, target):
                return delegation
        return None

    @staticmethod
    def _audit(event_type: str, actor_id: str, details: dict[str, Any]) -> None:
        result = IpcClient("stated").call(
            "audit.append", {"event_type": event_type, "actor_id": actor_id, "details": details}
        )
        if not isinstance(result, dict) or result.get("status") != "appended":
            raise RuntimeError("delegation audit append failed")
