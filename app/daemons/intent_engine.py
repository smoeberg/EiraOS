from __future__ import annotations

import os

from app.capability import list_manifests
from app.intent_parser import list_trust_items, parse_intent_request, plan_intent
from app.ipc.access import caller, open_write, read
from app.ipc.auth import PEER_KEY
from app.ipc.jsonrpc import JsonRpcError
from app.journey import get_journey, list_journeys
from app.mistral import is_mistral_available
from app.models import ParseIntentRequest
from app.pending_intents import save_pending
from app.session_store import ensure_session, mode_for_uid, session_of_caller, set_mode_for_uid


def _caller_uid(params: dict) -> int | None:
    """The OS user on the socket (SO_PEERCRED). None outside a socket."""
    peer = params.pop(PEER_KEY, None)
    uid = getattr(peer, "uid", None)
    return uid if isinstance(uid, int) else None


def _with_peer(handler):
    handler.wants_peer = True
    return handler


def _session_id(params: dict) -> str:
    # A client-named actor is never stored (fundregister S-5). Which session
    # a pending intent belongs to is decided by the caller's UID in F1.2,
    # when the IntentBar goes through modeld and the gate.
    return ensure_session(params.get("session_id"))


@_with_peer
def dashboard_get(params: dict) -> dict:
    """The dashboard for the OS user on the socket. Never creates a session
    and never echoes an identity the client claims (fundregister S-5): the
    greeting comes from the caller's own authenticated session, if any."""
    uid = _caller_uid(params)
    session = session_of_caller(uid, params.get("session_id")) if uid is not None else None
    return {
        "greeting": f"Hej {session['actor_name'] if session else 'bruger'}",
        "focus": "Kommunepilot",
        "state": "Arbejde",
        "session_id": session["session_id"] if session else None,
        "actor_id": session["actor_id"] if session else None,
        "authenticated": session is not None,
        "trust_items": [t.model_dump(mode="json") for t in list_trust_items()],
        "active_journeys": [j.model_dump(mode="json") for j in list_journeys()],
        "mistral_available": is_mistral_available(),
        "presentation_mode": _mode(uid),
    }


def intent_parse(params: dict) -> dict:
    sid = _session_id(params)
    body = ParseIntentRequest.model_validate(params)
    intent = parse_intent_request(body)
    payload = intent.model_dump(mode="json")
    save_pending(sid, intent.intent_id, payload)
    return payload


def intent_plan(params: dict) -> dict:
    sid = _session_id(params)
    body = ParseIntentRequest.model_validate(params)
    planned = plan_intent(body)
    payload = planned.model_dump(mode="json")
    save_pending(sid, planned.intent_id, payload)
    return payload


def journey_list(_params: dict) -> list:
    return [j.model_dump(mode="json") for j in list_journeys()]


def journey_get(params: dict) -> dict:
    journey_id = params.get("journey_id")
    if not journey_id:
        raise JsonRpcError(-32602, "journey_id required")
    journey = get_journey(journey_id)
    if not journey:
        raise JsonRpcError(-32602, "journey not found")
    return journey.model_dump(mode="json")


def capability_list(_params: dict) -> list:
    return [m.model_dump(mode="json") for m in list_manifests()]


def builder_mode_allowed() -> bool:
    """Builder Mode (terminal, files, legacy apps) is policy-gated.

    Desktop Architecture v1.0: Explorer users get no escape hatch unless IT
    policy allows Builder. Until the governance agent compiles policy, the
    switch is the EIRA_BUILDER_MODE_ALLOWED environment setting.
    """
    value = os.environ.get("EIRA_BUILDER_MODE_ALLOWED", "")
    return value.strip().lower() in {"1", "true", "yes"}


def _mode(uid: int | None) -> str:
    """Explorer unless this OS user chose Builder and policy still allows it."""
    if uid is None:
        return "explorer"
    mode = mode_for_uid(uid)
    if mode == "builder" and not builder_mode_allowed():
        # Policy revoked after the switch: fall back to Explorer.
        mode = set_mode_for_uid(uid, "explorer")
    return mode


@_with_peer
def presentation_mode_get(params: dict) -> dict:
    """The mode belongs to the OS user on the socket, so the terminal's own
    check (ui/src-tauri) sees the same mode the UI switched to (F1.5)."""
    uid = _caller_uid(params)
    return {"mode": _mode(uid), "builder_allowed": builder_mode_allowed()}


@_with_peer
def presentation_mode_set(params: dict) -> dict:
    uid = _caller_uid(params)
    mode = params.get("mode", "explorer")
    if mode not in ("explorer", "builder"):
        raise JsonRpcError(-32602, "mode must be explorer or builder")
    if uid is None:
        raise JsonRpcError(-32003, "caller_required", {"user_message": "Tilstanden kan kun skiftes fra skrivebordet"})
    # Builder access is device/IT policy, never a client-supplied flag.
    # Fail closed: Builder stays off unless the installed policy enables it.
    if mode == "builder" and not builder_mode_allowed():
        raise JsonRpcError(-32003, "builder_not_allowed", {"user_message": "Builder Mode er ikke tilladt"})
    return {"mode": set_mode_for_uid(uid, mode)}


def register_intent_handlers(server) -> None:
    # The caller is the OS user on the socket (F1.5); no session is created.
    server.register("dashboard.get", caller(dashboard_get))
    # Old parse/plan keep pending intents for a claimed session: open writes
    # until F1.2 removes them.
    server.register("intent.parse", open_write(intent_parse, "F1.2"))
    server.register("intent.plan", open_write(intent_plan, "F1.2"))
    # Protected writes go through Gate Kernel only (specs/GATE-KERNEL-1.0.md §2).
    from app.gate.ipc import gate_required

    server.register("intent.confirm", gate_required("intent.confirm"))
    server.register("journey.list", read(journey_list))
    server.register("journey.get", read(journey_get))
    server.register("journey.advance", gate_required("journey.advance"))
    server.register("capability.list", read(capability_list))
    server.register("presentation.mode_get", caller(presentation_mode_get))
    server.register("presentation.mode_set", caller(presentation_mode_set))
    server.register("health", read(lambda _: {"daemon": "eira-intent-engine", "ok": True}))
