from fastapi import APIRouter
from app.routers.common import fleet_ipc, graph_ipc, identity_ipc, intent_ipc, ipc_http

router = APIRouter(tags=["Health"])

@router.get("/health")
def health() -> dict:
    try:
        intent_ok = intent_ipc.call("health")
        identity_ok = identity_ipc.call("health")
        graph_ok = graph_ipc.call("health")
        fleet_ok = fleet_ipc.call("health")
        return {
            "status": "ok",
            "phase": "4-p0",
            "transport": "ipc",
            "daemons": {
                "intent": intent_ok,
                "identity": identity_ok,
                "graph": graph_ok,
                "fleet": fleet_ok,
            },
        }
    except Exception as exc:
        raise ipc_http(exc) from exc
