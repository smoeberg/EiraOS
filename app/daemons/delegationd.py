from __future__ import annotations
from typing import Any
from app.auth.delegation import DelegationCheckRequest,DelegationCreateRequest,DelegationRevokeRequest,DelegationService
from app.gate.caller import Caller,from_peer
from app.ipc.auth import PEER_KEY
from app.ipc.jsonrpc import JsonRpcError
_SERVICE=DelegationService()
def _caller(params):
    caller=from_peer(params.pop(PEER_KEY,None))
    if caller is None:raise JsonRpcError(-32001,"No caller context")
    return caller
def _identity(caller,session_id):
    if caller.model or not session_id:raise JsonRpcError(-32003,"Authenticated human session required")
    from app.session_store import get_session_for_gate
    s=get_session_for_gate(session_id)
    if not s or not s.get("authenticated_at"):raise JsonRpcError(-32003,"Invalid authenticated session")
    if s.get("os_uid") is None or int(s["os_uid"])!=caller.uid:raise JsonRpcError(-32003,"Session is not bound to this OS user")
    return str(s.get("identity") or s.get("actor_id") or "")
def register_delegation_handlers(server):
    def create(p):
        c=_caller(p);delegator=_identity(c,p.get("session_id"));req=DelegationCreateRequest.model_validate(p)
        try:d=_SERVICE.create_delegation(delegator,req)
        except (PermissionError,ValueError,RuntimeError) as e:raise JsonRpcError(-32003,str(e)) from e
        return {"status":"created","delegation_id":d.id,"delegator_id":d.delegator_id,"delegee_id":d.delegee_id,"scope":d.scope.model_dump(),"expires_at":d.expires_at.isoformat()}
    create.wants_peer=True
    def revoke(p):
        c=_caller(p);delegator=_identity(c,p.get("session_id"))
        try:ok=_SERVICE.revoke_delegation(DelegationRevokeRequest(delegation_id=str(p["delegation_id"])),delegator)
        except (PermissionError,ValueError,RuntimeError) as e:raise JsonRpcError(-32003,str(e)) from e
        return {"status":"revoked" if ok else "not_found"}
    revoke.wants_peer=True
    def check(p):return {"valid":_SERVICE.check_delegation(DelegationCheckRequest.model_validate(p))}
    def listing(p):
        c=_caller(p);delegator=_identity(c,p.get("session_id"));rows=_SERVICE.repo.active_for_delegator(delegator)
        return {"delegations":[{"id":d.id,"delegee_id":d.delegee_id,"scope":d.scope.model_dump(),"expires_at":d.expires_at.isoformat(),"created_at":d.created_at.isoformat()} for d in rows]}
    listing.wants_peer=True
    server.register("delegation.create",create);server.register("delegation.revoke",revoke);server.register("delegation.check",check);server.register("delegation.list",listing);server.register("health",lambda _:{"daemon":"eira-delegationd","ok":True})
