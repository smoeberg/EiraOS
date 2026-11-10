from __future__ import annotations

from app.auth.delegation import (
    DelegationCheckRequest,
    DelegationCreateRequest,
    DelegationRevokeRequest,
    DelegationService,
)
from app.gate.caller import from_peer
from app.ipc.auth import PEER_KEY
from app.ipc.jsonrpc import JsonRpcError

_SERVICE = DelegationService()


def _caller(params):
    caller = from_peer(params.pop(PEER_KEY, None))
    if caller is None:
        raise JsonRpcError(-32001, "No caller context")
    return caller


def _identity(caller, session_id):
    if caller.model or not session_id:
        raise JsonRpcError(-32003, "Authenticated human session required")

    from app.session_store import get_session_for_gate

    session = get_session_for_gate(session_id)
    if not session or not session.get("authenticated_at"):
        raise JsonRpcError(-32003, "Invalid authenticated session")
    if session.get("os_uid") is None or int(session["os_uid"]) != caller.uid:
        raise JsonRpcError(-32003, "Session is not bound to this OS user")
    return str(session.get("identity") or session.get("actor_id") or "")


def register_delegation_handlers(server):
    def create(params):
        caller = _caller(params)
        delegator = _identity(caller, params.get("session_id"))
        request = DelegationCreateRequest.model_validate(params)
        try:
            delegation = _SERVICE.create_delegation(delegator, request)
        except (PermissionError, ValueError, RuntimeError) as error:
            raise JsonRpcError(-32003, str(error)) from error
        return {
            "status": "created",
            "delegation_id": delegation.id,
            "delegator_id": delegation.delegator_id,
            "delegee_id": delegation.delegee_id,
            "scope": delegation.scope.model_dump(),
            "expires_at": delegation.expires_at.isoformat(),
        }

    create.wants_peer = True

    def revoke(params):
        caller = _caller(params)
        delegator = _identity(caller, params.get("session_id"))
        try:
            success = _SERVICE.revoke_delegation(
                DelegationRevokeRequest(delegation_id=str(params["delegation_id"])),
                delegator,
            )
        except (PermissionError, ValueError, RuntimeError) as error:
            raise JsonRpcError(-32003, str(error)) from error
        return {"status": "revoked" if success else "not_found"}

    revoke.wants_peer = True

    def check(params):
        return {
            "valid": _SERVICE.check_delegation(
                DelegationCheckRequest.model_validate(params)
            )
        }

    def listing(params):
        caller = _caller(params)
        delegator = _identity(caller, params.get("session_id"))
        rows = _SERVICE.repo.active_for_delegator(delegator)
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

    listing.wants_peer = True

    server.register("delegation.create", create)
    server.register("delegation.revoke", revoke)
    server.register("delegation.check", check)
    server.register("delegation.list", listing)
    server.register(
        "health",
        lambda _: {"daemon": "eira-delegationd", "ok": True},
    )
