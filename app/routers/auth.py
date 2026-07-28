import os
from urllib.parse import urlencode
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import RedirectResponse

from app.auth.oidc import (
    complete_oidc_callback,
    load_oidc_config,
    mock_login,
    start_oidc_login,
)
from app.ipc.jsonrpc import JsonRpcError
from app.routers.common import identity_ipc, sid

router = APIRouter(prefix="/v1", tags=["Authentication & Identity"])

@router.get("/auth/oidc/config")
def oidc_config():
    return load_oidc_config().to_public_dict()

@router.get("/auth/oidc/login")
def oidc_login(redirect: bool = True):
    try:
        result = start_oidc_login()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if redirect:
        return RedirectResponse(result["authorize_url"])
    return result

@router.get("/auth/oidc/callback")
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

@router.post("/auth/oidc/mock-login")
def oidc_mock_login(body: dict):
    try:
        return mock_login(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

@router.get("/identity/session")
def identity_session(x_eira_session_id: str | None = Header(default=None, alias="X-EIRA-Session-Id")):
    return identity_ipc.call("identity.session", {}, session_id=sid(x_eira_session_id))

@router.post("/identity/step-up")
def identity_step_up(
    body: dict,
    x_eira_session_id: str | None = Header(default=None, alias="X-EIRA-Session-Id"),
):
    try:
        return identity_ipc.call("identity.step_up", body, session_id=sid(x_eira_session_id))
    except JsonRpcError as exc:
        raise HTTPException(status_code=400, detail=exc.data or exc.message) from exc
