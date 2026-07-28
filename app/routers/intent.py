from fastapi import APIRouter, Header, HTTPException
from app.ipc.jsonrpc import JsonRpcError
from app.models import ParseIntentRequest
from app.routers.common import intent_ipc, ipc_http, sid

router = APIRouter(prefix="/v1/intent", tags=["Intent"])

@router.post("/parse")
def intent_parse(body: ParseIntentRequest):
    try:
        return intent_ipc.call("intent.parse", body.model_dump())
    except Exception as exc:
        raise ipc_http(exc) from exc

@router.post("/plan")
def intent_plan(
    body: ParseIntentRequest,
    x_eira_session_id: str | None = Header(default=None, alias="X-EIRA-Session-Id"),
):
    try:
        payload = body.model_dump()
        return intent_ipc.call("intent.plan", payload, session_id=sid(x_eira_session_id))
    except Exception as exc:
        raise ipc_http(exc) from exc

@router.post("/confirm")
def intent_confirm(
    body: dict,
    x_eira_session_id: str | None = Header(default=None, alias="X-EIRA-Session-Id"),
):
    try:
        return intent_ipc.call("intent.confirm", body, session_id=sid(x_eira_session_id))
    except JsonRpcError as exc:
        raise HTTPException(status_code=400, detail=exc.data or exc.message) from exc
