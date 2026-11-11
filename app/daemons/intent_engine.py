from __future__ import annotations

import os

from app.capability import list_manifests
from app.intent_parser import list_trust_items, parse_intent_request, plan_intent
from app.ipc.jsonrpc import JsonRpcError
from app.journey import get_journey, list_journeys
from app.mistral import is_mistral_available
from app.models import ParseIntentRequest
from app.pending_intents import save_pending
from app.session_store import (
    ensure_session,
    get_presentation_mode,
    get_session,
    set_presentation_mode,
)


def _session_id(params: dict) -> str:
    return ensure_session(params.get("session_id"), params.get("actor_id"))


def dashboard_get(params: dict) -> dict:
    sid = _session_id(params)
    session = get_session(sid)
    return {
        "greeting": f"Hej {session['actor_name'] if session else 'bruger'}",
        "focus": "Kommunepilot",
        "state": "Arbejde",
        "session_id": sid,
        "actor_id": session["actor_id"] if session else params.get("actor_id"),
        "trust_items": [t.model_dump(mode="json") for t in list_trust_items()],
        "active_journeys": [j.model_dump(mode="json") for j in list_journeys()],
        "mistral_available": is_mistral_available(),
        "presentation_mode": get_presentation_mode(sid),
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


def presentation_mode_get(params: dict) -> dict:
    sid = _session_id(params)
    mode = get_presentation_mode(sid)
    if mode == "builder" and not builder_mode_allowed():
        # Policy revoked after the switch: fall back to Explorer.
        mode = "explorer"
        set_presentation_mode(sid, mode)
    return {"mode": mode, "session_id": sid, "builder_allowed": builder_mode_allowed()}


def presentation_mode_set(params: dict) -> dict:
    sid = _session_id(params)
    mode = params.get("mode", "explorer")
    if mode not in ("explorer", "builder"):
        raise JsonRpcError(-32602, "mode must be explorer or builder")
    # Builder access is device/IT policy, never a client-supplied flag.
    # Fail closed: Builder stays off unless the installed policy enables it.
    if mode == "builder" and not builder_mode_allowed():
        raise JsonRpcError(-32003, "builder_not_allowed", {"user_message": "Builder Mode er ikke tilladt"})
    set_presentation_mode(sid, mode)
    return {"mode": mode, "session_id": sid}


def register_intent_handlers(server) -> None:
    server.register("dashboard.get", dashboard_get)
    server.register("intent.parse", intent_parse)
    server.register("intent.plan", intent_plan)
    # Protected writes go through Gate Kernel only (specs/GATE-KERNEL-1.0.md §2).
    from app.gate.ipc import gate_required

    server.register("intent.confirm", gate_required("intent.confirm"))
    server.register("journey.list", journey_list)
    server.register("journey.get", journey_get)
    server.register("journey.advance", gate_required("journey.advance"))
    server.register("capability.list", capability_list)
    server.register("presentation.mode_get", presentation_mode_get)
    server.register("presentation.mode_set", presentation_mode_set)
    server.register("health", lambda _: {"daemon": "eira-intent-engine", "ok": True})
