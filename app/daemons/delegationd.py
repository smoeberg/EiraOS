"""eira-delegationd: "på vegne af" over IPC (EIRA-DELEGATION-1.0).

Creating a delegation is a decision and follows the gate's trusted path:

1. ``delegation.propose`` validates the request and returns the exact text the
   user will approve (``rendering``) with its hash and the content hash.
2. ``delegation.create`` needs a proof made with the session's consent key
   (``app/gate/consent_proof.py``, verb ``delegate``). Only the desktop app's
   Rust core holds that key, so another program running as the user, even
   with the session id, cannot delegate.

Revoking needs only the user's own session: it takes power away.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.auth.delegation import (
    DelegationCheckRequest,
    DelegationCreateRequest,
    DelegationRevokeRequest,
    DelegationService,
)
from app.gate import consent_proof
from app.gate.caller import Caller, from_peer, model_identity
from app.ipc.access import caller, read
from app.ipc.auth import PEER_KEY
from app.ipc.jsonrpc import JsonRpcError

_SERVICE = DelegationService()

NO_CALLER = -32001
NOT_ALLOWED = -32003
BAD_PROOF = -32004


def _caller(params: dict[str, Any]) -> Caller:
    caller = from_peer(params.pop(PEER_KEY, None))
    if caller is None:
        raise JsonRpcError(NO_CALLER, "No caller context")
    return caller


def _session(caller: Caller, session_id: Any) -> dict[str, Any]:
    if caller.model or not isinstance(session_id, str) or not session_id:
        raise JsonRpcError(NOT_ALLOWED, "Authenticated human session required")

    from app.session_store import get_session_for_gate

    session = get_session_for_gate(session_id)
    if not session or not session.get("authenticated_at"):
        raise JsonRpcError(NOT_ALLOWED, "Invalid authenticated session")
    if session.get("os_uid") is None or int(session["os_uid"]) != caller.uid:
        raise JsonRpcError(NOT_ALLOWED, "Session is not bound to this OS user")
    return session


def _require_agent(caller: Caller) -> None:
    """On an installed system only the consent agent may decide (its
    effective gid, EIRA-CONSENT-AGENT §7); a development machine keeps the
    app's path, like the gate."""
    from app.gate.caller import installed

    if installed() and not caller.consent_agent:
        raise JsonRpcError(BAD_PROOF, "E_CONSENT_PATH",
                           {"user_message": "Delegation gives gennem EiraOS' samtykkevindue."})


def _identity(session: dict[str, Any]) -> str:
    return str(session.get("identity") or session.get("actor_id") or "")


def _text(params: dict[str, Any], name: str) -> str:
    value = params.get(name)
    if not isinstance(value, str) or not value:
        raise JsonRpcError(-32602, f"{name} is required")
    return value


def register_delegation_handlers(server, service: DelegationService | None = None) -> None:
    svc = service or _SERVICE

    def propose(params: dict[str, Any]) -> dict[str, Any]:
        caller = _caller(params)
        session = _session(caller, params.get("session_id"))
        try:
            request = DelegationCreateRequest.model_validate(
                {k: v for k, v in params.items() if k not in ("session_id", "_eira")}
            )
            return svc.propose_delegation(_identity(session), params["session_id"], request)
        except ValidationError as error:
            raise JsonRpcError(-32602, "invalid delegation request", {"errors": error.errors()}) from None
        except (PermissionError, ValueError) as error:
            raise JsonRpcError(NOT_ALLOWED, str(error)) from None

    def proposal(params: dict[str, Any]) -> dict[str, Any]:
        """What the consent agent shows (EIRA-CONSENT-AGENT §5.4): the text
        fixed at propose time, read here and never taken from the app."""
        caller = _caller(params)
        _require_agent(caller)
        session = _session(caller, params.get("session_id"))
        found = svc.repo.proposal(_text(params, "proposal_id"), _identity(session), params["session_id"])
        if found is None:
            raise JsonRpcError(NOT_ALLOWED, "unknown, expired or used proposal")
        return {
            "proposal_id": found["id"],
            "content_hash": found["content_hash"],
            "rendering": {"text": found["rendering_text"], "hash": found["rendering_hash"], "lang": "da"},
        }

    def create(params: dict[str, Any]) -> dict[str, Any]:
        caller = _caller(params)
        _require_agent(caller)
        session = _session(caller, params.get("session_id"))
        proposal_id = _text(params, "proposal_id")
        content_hash = _text(params, "content_hash")
        rendering_hash = _text(params, "rendering_hash")
        if not consent_proof.verify(
            session.get("consent_key"), params.get("proof"), "delegate", caller.uid,
            params["session_id"], proposal_id, content_hash, rendering_hash,
        ):
            raise JsonRpcError(BAD_PROOF, "E_CONSENT_PROOF",
                               {"user_message": "Delegation kan kun gives fra EiraOS-appen."})
        try:
            delegation = svc.activate(_identity(session), params["session_id"], proposal_id,
                                      content_hash, rendering_hash)
        except (PermissionError, ValueError, RuntimeError) as error:
            raise JsonRpcError(NOT_ALLOWED, str(error)) from None
        return {
            "status": "created",
            "delegation_id": delegation.id,
            "delegator_id": delegation.delegator_id,
            "delegee_id": delegation.delegee_id,
            "scope": delegation.scope.model_dump(),
            "expires_at": delegation.expires_at.isoformat(),
        }

    def revoke(params: dict[str, Any]) -> dict[str, Any]:
        caller = _caller(params)
        session = _session(caller, params.get("session_id"))
        try:
            success = svc.revoke_delegation(
                DelegationRevokeRequest(delegation_id=_text(params, "delegation_id")), _identity(session)
            )
        except (PermissionError, ValueError, RuntimeError) as error:
            raise JsonRpcError(NOT_ALLOWED, str(error)) from None
        return {"status": "revoked" if success else "not_found"}

    def check(params: dict[str, Any]) -> dict[str, Any]:
        # The model may ask about itself; a human about any model. Nobody
        # anonymous learns which delegations exist.
        caller = _caller(params)
        request = DelegationCheckRequest.model_validate(
            {k: params.get(k) for k in ("delegee_id", "action", "target")}
        )
        if caller.model and request.delegee_id != model_identity(caller):
            raise JsonRpcError(NOT_ALLOWED, "a model may only check its own delegations")
        return {"valid": svc.check_delegation(request)}

    def listing(params: dict[str, Any]) -> dict[str, Any]:
        caller = _caller(params)
        session = _session(caller, params.get("session_id"))
        rows = svc.repo.active_for_delegator(_identity(session))
        return {
            "delegations": [
                {
                    "id": delegation.id,
                    "delegee_id": delegation.delegee_id,
                    "scope": delegation.scope.model_dump(),
                    "expires_at": delegation.expires_at.isoformat(),
                    "created_at": delegation.created_at.isoformat(),
                }
                for delegation in rows
            ]
        }

    for handler in (propose, proposal, create, revoke, check, listing):
        handler.wants_peer = True
    server.register("delegation.propose", caller(propose))
    server.register("delegation.proposal", caller(proposal))
    server.register("delegation.create", caller(create))
    server.register("delegation.revoke", caller(revoke))
    server.register("delegation.check", caller(check))
    server.register("delegation.list", caller(listing))
    server.register("health", read(lambda _: {"daemon": "eira-delegationd", "ok": True}))
