from __future__ import annotations

from app.ipc.jsonrpc import ASSURANCE_REQUIRED, JsonRpcError
from app.session_store import ensure_session, get_session, update_assurance


def _session_id_from(params: dict) -> str:
    sid = params.get("session_id")
    actor = params.get("actor_id")
    return ensure_session(sid, actor)


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
    step_up_token = params.get("step_up_token") or params.get("challenge_response")

    if method != "mitid_erhverv":
        raise JsonRpcError(
            ASSURANCE_REQUIRED,
            "unsupported_step_up",
            {"user_message": f"Step-up metode '{method}' understøttes ikke"},
        )

    if not step_up_token:
        raise JsonRpcError(
            ASSURANCE_REQUIRED,
            "step_up_unverified",
            {"user_message": "MitID Erhverv verifikation påkrævet (ugyldig eller manglende step-up token)"},
        )

    session = update_assurance(sid, required)
    return {
        "session_id": sid,
        "assurance_level": session["assurance_level"],
        "user_message": "MitID Erhverv verifikation gennemført",
    }


def register_identity_handlers(server) -> None:
    server.register("identity.session", identity_session)
    server.register("identity.step_up", identity_step_up)
    server.register("health", lambda _: {"daemon": "eira-identityd", "ok": True})
