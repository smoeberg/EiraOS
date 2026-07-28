"""
HTTP dev bridge — translates REST to IPC (dev only).

Production: eira-shell (Tauri) calls Unix sockets directly.
See EIRA_Desktop_Architecture_v1.0.md §6.1 anti-pattern.
"""

from __future__ import annotations

import json
import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import urlencode

from fastapi.responses import RedirectResponse

from app.auth.oidc import (
    complete_oidc_callback,
    load_oidc_config,
    mock_login,
    start_oidc_login,
)
from app.capability import get_manifest
from app.daemons.runner import start_daemons
from app.ipc.client import IpcClient
from app.ipc.jsonrpc import JsonRpcError
from app.models import (
    AuditEvent,
    DashboardResponse,
    GraphContextResponse,
    ParseIntentRequest,
    TemporalQueryRequest,
)
from app.database import get_connection

app = FastAPI(
    title="EIRA HTTP Dev Bridge",
    description="REST → IPC bridge for React UI during development. Not for production.",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

intent_ipc = IpcClient("intent")
identity_ipc = IpcClient("identity")
graph_ipc = IpcClient("graph")
fleet_ipc = IpcClient("fleet")


def _sid(header: str | None) -> str | None:
    return header.strip() if header else None


@app.on_event("startup")
def startup() -> None:
    start_daemons()


def _ipc_http(exc: Exception) -> HTTPException:
    if isinstance(exc, JsonRpcError):
        return HTTPException(
            status_code=400,
            detail={
                "code": exc.code,
                "message": exc.message,
                "data": exc.data,
            },
        )
    if isinstance(exc, ConnectionError):
        return HTTPException(status_code=503, detail=str(exc))
    raise exc


@app.get("/health")
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
        raise _ipc_http(exc) from exc


@app.get("/v1/dashboard", response_model=DashboardResponse)
def dashboard(x_eira_session_id: str | None = Header(default=None, alias="X-EIRA-Session-Id")):
    try:
        result = intent_ipc.call(
            "dashboard.get",
            {"actor_id": "mette@kommune.dk"},
            session_id=_sid(x_eira_session_id),
        )
        return DashboardResponse.model_validate(result)
    except Exception as exc:
        raise _ipc_http(exc) from exc


@app.get("/v1/trust")
def trust_items():
    data = intent_ipc.call("dashboard.get")
    return data["trust_items"]


@app.get("/v1/capabilities")
def capabilities():
    return intent_ipc.call("capability.list")


@app.get("/v1/capabilities/{adapter_id}")
def capability_detail(adapter_id: str):
    for manifest in intent_ipc.call("capability.list"):
        if manifest["adapter_id"] == adapter_id:
            return manifest
    manifest = get_manifest(adapter_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Capability manifest not found")
    return manifest


@app.get("/v1/journeys")
def journeys():
    return intent_ipc.call("journey.list")


@app.get("/v1/journeys/{journey_id}")
def journey_detail(journey_id: str):
    try:
        return intent_ipc.call("journey.get", {"journey_id": journey_id})
    except JsonRpcError as exc:
        if exc.message == "journey not found":
            raise HTTPException(status_code=404, detail="Journey not found") from exc
        raise _ipc_http(exc) from exc


@app.post("/v1/journeys/{journey_id}/advance")
def journey_advance(journey_id: str):
    try:
        return intent_ipc.call("journey.advance", {"journey_id": journey_id})
    except JsonRpcError as exc:
        if exc.message == "journey not found":
            raise HTTPException(status_code=404, detail="Journey not found") from exc
        raise _ipc_http(exc) from exc


@app.post("/v1/intent/parse")
def intent_parse(body: ParseIntentRequest):
    try:
        return intent_ipc.call("intent.parse", body.model_dump())
    except Exception as exc:
        raise _ipc_http(exc) from exc


@app.post("/v1/intent/plan")
def intent_plan(
    body: ParseIntentRequest,
    x_eira_session_id: str | None = Header(default=None, alias="X-EIRA-Session-Id"),
):
    try:
        payload = body.model_dump()
        return intent_ipc.call("intent.plan", payload, session_id=_sid(x_eira_session_id))
    except Exception as exc:
        raise _ipc_http(exc) from exc


@app.post("/v1/intent/confirm")
def intent_confirm(
    body: dict,
    x_eira_session_id: str | None = Header(default=None, alias="X-EIRA-Session-Id"),
):
    try:
        return intent_ipc.call("intent.confirm", body, session_id=_sid(x_eira_session_id))
    except JsonRpcError as exc:
        raise HTTPException(status_code=400, detail=exc.data or exc.message) from exc


@app.get("/v1/auth/oidc/config")
def oidc_config():
    return load_oidc_config().to_public_dict()


@app.get("/v1/auth/oidc/login")
def oidc_login(redirect: bool = True):
    try:
        result = start_oidc_login()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if redirect:
        return RedirectResponse(result["authorize_url"])
    return result


@app.get("/v1/auth/oidc/callback")
def oidc_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    ui_redirect: bool = True,
):
    try:
        result = complete_oidc_callback(
            code=code,
            state=state,
            error=error,
            error_description=error_description,
        )
        if ui_redirect:
            base = os.environ.get("OIDC_UI_REDIRECT_URI", "http://localhost:5173/").rstrip("/")
            params = urlencode({"session_id": result["session_id"]})
            return RedirectResponse(f"{base}/?{params}")
        return result
    except ValueError as exc:
        if ui_redirect:
            base = os.environ.get("OIDC_UI_REDIRECT_URI", "http://localhost:5173/").rstrip("/")
            params = urlencode({"auth_error": str(exc)})
            return RedirectResponse(f"{base}/?{params}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/auth/oidc/mock-login")
def oidc_mock_login(body: dict):
    try:
        return mock_login(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.get("/v1/identity/session")
def identity_session(x_eira_session_id: str | None = Header(default=None, alias="X-EIRA-Session-Id")):
    return identity_ipc.call("identity.session", {}, session_id=_sid(x_eira_session_id))


@app.post("/v1/identity/step-up")
def identity_step_up(
    body: dict,
    x_eira_session_id: str | None = Header(default=None, alias="X-EIRA-Session-Id"),
):
    try:
        return identity_ipc.call("identity.step_up", body, session_id=_sid(x_eira_session_id))
    except JsonRpcError as exc:
        raise HTTPException(status_code=400, detail=exc.data or exc.message) from exc


@app.post("/v1/fleet/enroll")
def fleet_enroll(body: dict):
    try:
        return fleet_ipc.call("fleet.enroll", body)
    except Exception as exc:
        raise _ipc_http(exc) from exc


@app.post("/v1/fleet/heartbeat")
def fleet_heartbeat(body: dict):
    try:
        return fleet_ipc.call("fleet.heartbeat", body)
    except Exception as exc:
        raise _ipc_http(exc) from exc


@app.get("/v1/fleet/devices/{device_id}")
def fleet_device(device_id: str):
    try:
        return fleet_ipc.call("fleet.device.get", {"device_id": device_id})
    except Exception as exc:
        raise _ipc_http(exc) from exc


@app.get("/v1/graph/context", response_model=GraphContextResponse)
def graph_context_endpoint(
    object_id: str | None = None,
    title: str = "",
    summary: str = "",
    focus: str = "Kommunepilot",
    trust_score: int = 0,
    sources: str = "",
):
    try:
        source_list = [s.strip() for s in sources.split(",") if s.strip()] if sources else []
        result = graph_ipc.call(
            "graph.context",
            {
                "object_id": object_id,
                "title": title,
                "summary": summary,
                "sources": source_list,
                "focus": focus,
                "trust_score": trust_score,
            },
        )
        return GraphContextResponse.model_validate(result)
    except Exception as exc:
        raise _ipc_http(exc) from exc


@app.post("/v1/graph/temporal")
def temporal_query(body: TemporalQueryRequest):
    try:
        return graph_ipc.call(
            "graph.temporal_query",
            body.model_dump(),
        )
    except Exception as exc:
        raise _ipc_http(exc) from exc


@app.get("/v1/audit")
def audit_log(limit: int = 20) -> list[AuditEvent]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        AuditEvent(
            id=row["id"],
            event_type=row["event_type"],
            payload=json.loads(row["payload"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]
