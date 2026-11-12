"""eira-modeld: the packaged model process (GATE-KERNEL bilag A).

Runs as ``eira-model`` (its own UID, not in the ``eira`` group), with no
network and no access to /data. One method:

``model.prepare {session_id, text, conversation_id, me, participants[], now?, lang?}``

1. The adapter reads the text (EiraLang) and proposes an action (EiraAI)
   inside the candidate list (AI-INTERFACE-1.0 §3, §5).
2. The model process wraps it in an EDP envelope with neutral transport and
   veritas (the adapter never sets those) and proposes it to the gate *as
   itself*: the gate sees the model UID (SO_PEERCRED), requires a
   delegation from the human whose session it is (EIRA Delegation v1.1),
   and the human must still consent and confirm on the trusted path.

The model process cannot verify who asked or which session is theirs: it
reads no session store. The gate decides; a wrong session or a missing
delegation is refused there.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from app.gate.caller import from_peer, model_uid
from app.ipc.access import caller, read
from app.ipc.auth import PEER_KEY
from app.ipc.jsonrpc import JsonRpcError
from app.model.contract import (
    MAX_PARTICIPANTS,
    MAX_TEXT,
    Abstain,
    ConversationContext,
    ModelAdapter,
    ModelError,
    Participant,
    checked_action,
    checked_extraction,
)
from app.model.rules import RuleAdapter

# Candidates the model may propose (§5.3: not a permission; the gate decides).
CANDIDATES = ("utterance", "commitment_proposed")
NO_CALLER = -32001
NOT_ALLOWED = -32003


def _context(params: dict[str, Any]) -> tuple[ConversationContext, str, str]:
    text, conversation, me = params.get("text"), params.get("conversation_id"), params.get("me")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise JsonRpcError(-32602, f"text is required (at most {MAX_TEXT} characters)")
    if not isinstance(conversation, str) or not conversation:
        raise JsonRpcError(-32602, "conversation_id is required")
    if not isinstance(me, str) or not me:
        raise JsonRpcError(-32602, "me (the requesting identity) is required")
    raw = params.get("participants") or []
    if not isinstance(raw, list) or len(raw) > MAX_PARTICIPANTS:
        raise JsonRpcError(-32602, f"participants must be a list of at most {MAX_PARTICIPANTS}")
    people = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("identity"), str):
            raise JsonRpcError(-32602, "each participant needs an identity")
        people.append(Participant(item["identity"], str(item.get("role", "member")), str(item.get("name", ""))))
    now = params.get("now") or datetime.now(timezone.utc).isoformat()
    if not isinstance(now, str):
        raise JsonRpcError(-32602, "now must be an ISO 8601 string")
    return ConversationContext(conversation, tuple(people), now), text, me


def _envelope(action, context: ConversationContext, me: str) -> dict[str, Any]:
    participants = [{"identity": me, "role": "member"}]
    participants += [{"identity": p.identity, "role": p.role} for p in action.participants if p.identity != me]
    return {
        "edp": "1.0",
        "id": "mdl-" + uuid.uuid4().hex,
        "conversation_id": context.conversation_id,
        "participants": participants,
        "action": {"type": action.type, "content": action.content},
        # Neutral, set here and not by the adapter (AI-INTERFACE §3.2).
        "transport": {"preferred": ["eira-native"], "actual": None, "degraded": False, "error": None},
        "veritas": {"status": "unassessed", "trust_score": None, "evidence_refs": []},
        "temporal": {"created_at": datetime.now(timezone.utc).isoformat(), "valid_from": None, "supersedes": None},
    }


def _gate_propose(envelope: dict[str, Any], session_id: str, lang: str) -> dict[str, Any]:
    from app.ipc.client import IpcClient

    return IpcClient("intentd").call(
        "gate.propose", {"edp": envelope, "session_id": session_id, "origin": "model", "lang": lang}
    )


def register_model_handlers(server, adapter: ModelAdapter | None = None, propose=_gate_propose) -> None:
    active = adapter or RuleAdapter()

    def prepare(params: dict[str, Any]) -> dict[str, Any]:
        caller = from_peer(params.pop(PEER_KEY, None))
        if caller is None:
            raise JsonRpcError(NO_CALLER, "No caller context")
        if caller.model:
            raise JsonRpcError(NOT_ALLOWED, "the model cannot ask itself")
        session_id = params.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise JsonRpcError(-32602, "session_id is required")
        context, text, me = _context(params)
        lang = params.get("lang", "da")
        about = {"adapter": active.name, "version": active.version}
        health = active.health()
        if not health.get("ok"):  # §4.3: an unhealthy adapter is not called
            return {"error": "E_MODEL_UNAVAILABLE", "model": about}
        intent = checked_extraction(active.extract_intent(text, context, params.get("language_hint")))
        if isinstance(intent, Abstain):
            return {"abstain": intent.reason, "model": about}
        if isinstance(intent, ModelError):
            return {"error": intent.code, "model": about}
        action = checked_action(active.propose_action(intent, CANDIDATES, context), CANDIDATES, context)
        if isinstance(action, Abstain):
            return {"abstain": action.reason, "model": about}
        if isinstance(action, ModelError):
            return {"error": action.code, "model": about}
        result = propose(_envelope(action, context, me), session_id, lang)
        return {"gate": result, "model": {**about, "intent": intent.intent, "confidence": intent.confidence}}

    prepare.wants_peer = True
    server.register("model.prepare", caller(prepare))
    server.register("health", read(lambda _: {"daemon": "eira-modeld", "ok": bool(active.health().get("ok")),
                                              "adapter": active.name}))


def main() -> int:
    """Refuses to run as anyone but ``eira-model``: under another UID its
    proposals would look like a human's to the gate."""
    import signal
    import threading

    from app.daemons.base import JsonRpcServer

    expected = model_uid()
    if expected is None or os.getuid() != expected:
        print("eira-modeld must run as the eira-model user", file=sys.stderr)
        return 78  # EX_CONFIG: systemd does not restart into the same error
    server = JsonRpcServer(name="eira-modeld", daemon="modeld")
    register_model_handlers(server)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    server.start()
    try:
        while not stop.wait(1.0):
            pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
