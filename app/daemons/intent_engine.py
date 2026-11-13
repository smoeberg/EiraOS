from __future__ import annotations

import os

from app.capability import list_manifests
from app.ipc.access import caller, read
from app.ipc.auth import PEER_KEY
from app.ipc.jsonrpc import JsonRpcError
from app.journey import get_journey, list_journeys
from app.session_store import mode_for_uid, session_of_caller, set_mode_for_uid
from app.trust_items import list_trust_items


def _caller_uid(params: dict) -> int | None:
    """The OS user on the socket (SO_PEERCRED). None outside a socket."""
    peer = params.pop(PEER_KEY, None)
    uid = getattr(peer, "uid", None)
    return uid if isinstance(uid, int) else None


def _with_peer(handler):
    handler.wants_peer = True
    return handler



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
        "presentation_mode": _mode(uid),
    }



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
    # Protected writes go through Gate Kernel only (specs/GATE-KERNEL-1.0.md §2).
    # The old intent.parse/intent.plan (pending intents for a claimed session,
    # an LLM client in the gate process) are gone (F1.2); an old client gets
    # E_GATE_REQUIRED, which names the way: the model process and gate.propose.
    from app.gate.ipc import gate_required

    for method in ("intent.parse", "intent.plan", "intent.confirm"):
        server.register(method, gate_required(method))
    server.register("journey.list", read(journey_list))
    server.register("journey.get", read(journey_get))
    server.register("journey.advance", gate_required("journey.advance"))
    server.register("capability.list", read(capability_list))
    server.register("presentation.mode_get", caller(presentation_mode_get))
    server.register("presentation.mode_set", caller(presentation_mode_set))
    server.register("health", read(lambda _: {"daemon": "eira-intent-engine", "ok": True}))
