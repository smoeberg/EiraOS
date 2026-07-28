from fastapi import APIRouter, Header, HTTPException
from app.capability import get_manifest
from app.ipc.jsonrpc import JsonRpcError
from app.models import DashboardResponse
from app.routers.common import intent_ipc, ipc_http, sid

router = APIRouter(prefix="/v1", tags=["Dashboard & Capabilities"])

@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(x_eira_session_id: str | None = Header(default=None, alias="X-EIRA-Session-Id")):
    try:
        result = intent_ipc.call(
            "dashboard.get",
            {"actor_id": "mette@kommune.dk"},
            session_id=sid(x_eira_session_id),
        )
        return DashboardResponse.model_validate(result)
    except Exception as exc:
        raise ipc_http(exc) from exc

@router.get("/trust")
def trust_items():
    data = intent_ipc.call("dashboard.get")
    return data["trust_items"]

@router.get("/capabilities")
def capabilities():
    return intent_ipc.call("capability.list")

@router.get("/capabilities/{adapter_id}")
def capability_detail(adapter_id: str):
    for manifest in intent_ipc.call("capability.list"):
        if manifest["adapter_id"] == adapter_id:
            return manifest
    manifest = get_manifest(adapter_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Capability manifest not found")
    return manifest

@router.get("/journeys")
def journeys():
    return intent_ipc.call("journey.list")

@router.get("/journeys/{journey_id}")
def journey_detail(journey_id: str):
    try:
        return intent_ipc.call("journey.get", {"journey_id": journey_id})
    except JsonRpcError as exc:
        if exc.message == "journey not found":
            raise HTTPException(status_code=404, detail="Journey not found") from exc
        raise ipc_http(exc) from exc

@router.post("/journeys/{journey_id}/advance")
def journey_advance(journey_id: str):
    try:
        return intent_ipc.call("journey.advance", {"journey_id": journey_id})
    except JsonRpcError as exc:
        if exc.message == "journey not found":
            raise HTTPException(status_code=404, detail="Journey not found") from exc
        raise ipc_http(exc) from exc
