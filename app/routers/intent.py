from fastapi import APIRouter, Header, HTTPException

from app.ipc.jsonrpc import JsonRpcError
from app.routers.common import intent_ipc, sid

router = APIRouter(prefix="/v1/intent", tags=["Intent"])

# The old /parse and /plan routes are gone with intent.parse/intent.plan
# (UDVIKLINGSPLAN F1.2): a sentence goes to eira-modeld and the gate.


@router.post("/confirm")
def intent_confirm(
    body: dict,
    x_eira_session_id: str | None = Header(default=None, alias="X-EIRA-Session-Id"),
):
    try:
        return intent_ipc.call("intent.confirm", body, session_id=sid(x_eira_session_id))
    except JsonRpcError as exc:
        raise HTTPException(status_code=400, detail=exc.data or exc.message) from exc
