from fastapi import APIRouter
from app.routers.common import fleet_ipc, ipc_http

router = APIRouter(prefix="/v1/fleet", tags=["Fleet Management"])

@router.post("/enroll")
def fleet_enroll(body: dict):
    try:
        return fleet_ipc.call("fleet.enroll", body)
    except Exception as exc:
        raise ipc_http(exc) from exc

@router.post("/heartbeat")
def fleet_heartbeat(body: dict):
    try:
        return fleet_ipc.call("fleet.heartbeat", body)
    except Exception as exc:
        raise ipc_http(exc) from exc

@router.get("/devices/{device_id}")
def fleet_device(device_id: str):
    try:
        return fleet_ipc.call("fleet.device.get", {"device_id": device_id})
    except Exception as exc:
        raise ipc_http(exc) from exc
