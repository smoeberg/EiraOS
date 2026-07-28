from __future__ import annotations

from app.ipc.jsonrpc import ASSURANCE_REQUIRED, JsonRpcError
from app.session_store import ensure_session, get_session, update_assurance


def _session_id_from(params: dict) -> str:
    return ensure_session(params.get("session_id"), params.get("actor_id"))


def get_session_for_actor() -> dict:
    """Backward compat for intent_engine imports."""
    from app.session_store import DEFAULT_ACTOR, ensure_session

    sid = ensure_session(None, DEFAULT_ACTOR["actor_id"])
    return get_session(sid) or {}


def identity_session(params: dict) -> dict:
    sid = _session_id_from(params)
    session = get_session(sid)
    if not session:
        raise JsonRpcError(-32602, "session not found")
    return session


def identity_step_up(params: dict) -> dict:
    sid = _session_id_from(params)
    required = params.get("required_assurance", "org_acting")
    method = params.get("method", "mitid_erhverv")

    if method != "mitid_erhverv":
        raise JsonRpcError(
            ASSURANCE_REQUIRED,
            "unsupported_step_up",
            {"user_message": f"Step-up metode '{method}' understøttes ikke i prototype"},
        )

    session = update_assurance(sid, required)
    return {
        "session_id": sid,
        "assurance_level": session["assurance_level"],
        "user_message": "MitID Erhverv gennemført (prototype stub)",
    }


def register_identity_handlers(server) -> None:
    server.register("identity.session", identity_session)
    server.register("identity.step_up", identity_step_up)
    server.register("health", lambda _: {"daemon": "eira-identityd", "ok": True})
