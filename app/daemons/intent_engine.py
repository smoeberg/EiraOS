from __future__ import annotations

import json
import uuid

from app.capability import list_manifests
from app.database import get_connection, utc_now_iso
from app.executor import execute_intent
from app.intent_parser import list_trust_items, parse_intent_request, plan_intent
from app.ipc.jsonrpc import ASSURANCE_REQUIRED, JsonRpcError
from app.journey import advance_journey, get_journey, list_journeys
from app.mistral import is_mistral_available
from app.models import ParseIntentRequest
from app.pending_intents import (
    claim_pending,
    get_pending,
    mark_executed,
    mark_execution_failed,
    save_pending,
)
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


def intent_confirm(params: dict) -> dict:
    sid = _session_id(params)
    intent_id = params.get("intent_id")
    if not intent_id:
        raise JsonRpcError(-32602, "intent_id required")

    pending = get_pending(intent_id, sid)
    if not pending:
        raise JsonRpcError(-32602, "intent not found", {"intent_id": intent_id})

    if pending.get("status") == "clarification_needed":
        raise JsonRpcError(
            -32002,
            "cannot_execute",
            {"user_message": "Afklar intentionen før bekræftelse"},
        )

    required = pending.get("required_assurance")
    session = get_session(sid)
    current_assurance = session.get("assurance_level") if session else None
    if required and current_assurance != required:
        raise JsonRpcError(
            ASSURANCE_REQUIRED,
            "assurance_required",
            {
                "required": required,
                "current": current_assurance or "unknown",
                "user_message": (
                    "Denne handling kræver et højere eller specifikt "
                    "verificeret sikkerhedsniveau"
                ),
            },
        )

    # A negative plan decision is authoritative. Re-plan after changing
    # capabilities, resolving ambiguity, or completing a verified step-up.
    if pending.get("can_execute") is False:
        raise JsonRpcError(
            -32002,
            "cannot_execute",
            {"user_message": pending.get("block_reason", "Handling kan ikke udføres")},
        )

    if not claim_pending(intent_id, sid):
        raise JsonRpcError(
            -32002,
            "intent_not_pending",
            {
                "intent_id": intent_id,
                "user_message": (
                    "Intentionen er allerede under behandling eller er afsluttet"
                ),
            },
        )

    try:
        execution = execute_intent(pending)
    except Exception:
        # Keep the intent non-retryable after an execution attempt: once real
        # adapters exist, an exception may occur after an external side effect.
        mark_execution_failed(intent_id)
        raise

    mark_executed(intent_id)
    result = {
        "intent_id": intent_id,
        "session_id": sid,
        "status": "executed",
        "message": execution["message"],
        "execution": execution,
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO audit_events (id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                "intent.executed",
                json.dumps(result),
                utc_now_iso(),
            ),
        )
    return result


def journey_list(_params: dict) -> list:
    return [j.model_dump(mode="json") for j in list_journeys()]


def journey_advance(params: dict) -> dict:
    journey_id = params.get("journey_id")
    if not journey_id:
        raise JsonRpcError(-32602, "journey_id required")
    journey = advance_journey(journey_id)
    if not journey:
        raise JsonRpcError(-32602, "journey not found")
    return journey.model_dump(mode="json")


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


def presentation_mode_get(params: dict) -> dict:
    sid = _session_id(params)
    return {"mode": get_presentation_mode(sid), "session_id": sid}


def presentation_mode_set(params: dict) -> dict:
    sid = _session_id(params)
    mode = params.get("mode", "explorer")
    if mode not in ("explorer", "builder"):
        raise JsonRpcError(-32602, "mode must be explorer or builder")
    allowed = params.get("policy_allowed", True)
    if not allowed and mode == "builder":
        raise JsonRpcError(-32003, "builder_not_allowed", {"user_message": "Builder Mode er ikke tilladt"})
    set_presentation_mode(sid, mode)
    return {"mode": mode, "session_id": sid}


def register_intent_handlers(server) -> None:
    server.register("dashboard.get", dashboard_get)
    server.register("intent.parse", intent_parse)
    server.register("intent.plan", intent_plan)
    server.register("intent.confirm", intent_confirm)
    server.register("journey.list", journey_list)
    server.register("journey.get", journey_get)
    server.register("journey.advance", journey_advance)
    server.register("capability.list", capability_list)
    server.register("presentation.mode_get", presentation_mode_get)
    server.register("presentation.mode_set", presentation_mode_set)
    server.register("health", lambda _: {"daemon": "eira-intent-engine", "ok": True})
