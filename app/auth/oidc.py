"""OIDC / Entra ID login — CP-OIDC-001."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.auth.audit import record_auth_event
from app.database import get_connection, utc_now_iso
from app.session_store import create_session_from_claims

_STATE_TTL = timedelta(minutes=10)


@dataclass
class OidcConfig:
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: str
    tenant_id: str
    mock_enabled: bool

    def authority_base(self) -> str:
        if self.issuer:
            issuer = self.issuer.rstrip("/")
            if issuer.endswith("/v2.0"):
                return issuer[: -len("/v2.0")]
            return issuer
        tenant = self.tenant_id or "common"
        return f"https://login.microsoftonline.com/{tenant}"

    def authorize_url(self) -> str:
        return f"{self.authority_base()}/oauth2/v2.0/authorize"

    def token_url(self) -> str:
        return f"{self.authority_base()}/oauth2/v2.0/token"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "issuer": self.issuer or self.authority_base() + "/v2.0",
            "client_id": self.client_id or None,
            "redirect_uri": self.redirect_uri,
            "scopes": self.scopes,
            "mock_enabled": self.mock_enabled,
            "login_mode": "mock" if self.mock_enabled else "oidc",
            "login_path": "/v1/auth/oidc/mock-login" if self.mock_enabled else "/v1/auth/oidc/login",
            "callback_path": "/v1/auth/oidc/callback",
        }


def load_oidc_config() -> OidcConfig:
    client_id = os.environ.get("OIDC_CLIENT_ID", "").strip()
    force_mock = os.environ.get("EIRA_OIDC_MOCK", "").lower() in ("1", "true", "yes")
    mock_enabled = force_mock or not client_id
    tenant_id = os.environ.get("OIDC_TENANT_ID", "common").strip() or "common"
    issuer = os.environ.get("OIDC_ISSUER", "").strip()
    if not issuer and not mock_enabled:
        issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
    return OidcConfig(
        issuer=issuer,
        client_id=client_id,
        client_secret=os.environ.get("OIDC_CLIENT_SECRET", "").strip(),
        redirect_uri=os.environ.get(
            "OIDC_REDIRECT_URI", "http://localhost:8765/v1/auth/oidc/callback"
        ).strip(),
        scopes=os.environ.get("OIDC_SCOPES", "openid profile email").strip(),
        tenant_id=tenant_id,
        mock_enabled=mock_enabled,
    )


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _store_auth_state(state: str, code_verifier: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO oidc_auth_states (state, code_verifier, created_at) VALUES (?, ?, ?)",
            (state, code_verifier, utc_now_iso()),
        )


def _pop_auth_state(state: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT code_verifier, created_at FROM oidc_auth_states WHERE state = ?",
            (state,),
        ).fetchone()
        conn.execute("DELETE FROM oidc_auth_states WHERE state = ?", (state,))
    if row is None:
        return None
    created = datetime.strptime(row["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created > _STATE_TTL:
        return None
    return row["code_verifier"]


def start_oidc_login() -> dict[str, str]:
    """Build Entra authorize URL with PKCE state (live mode only)."""
    cfg = load_oidc_config()
    if cfg.mock_enabled:
        raise PermissionError("Mock mode active — use POST /v1/auth/oidc/mock-login")

    state = secrets.token_urlsafe(32)
    verifier, challenge = _pkce_pair()
    _store_auth_state(state, verifier)

    params = {
        "client_id": cfg.client_id,
        "response_type": "code",
        "redirect_uri": cfg.redirect_uri,
        "response_mode": "query",
        "scope": cfg.scopes,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return {
        "authorize_url": f"{cfg.authorize_url()}?{urlencode(params)}",
        "state": state,
    }


def _decode_jwt_payload_unverified(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("invalid id_token")
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def claims_from_id_token(id_token: str) -> dict[str, Any]:
    """Map Entra id_token claims to EIRA session fields (signature validation P2)."""
    payload = _decode_jwt_payload_unverified(id_token)
    email = str(
        payload.get("preferred_username")
        or payload.get("email")
        or payload.get("upn")
        or ""
    ).strip().lower()
    if not email:
        raise ValueError("id_token missing email claim")

    name = str(payload.get("name") or email.split("@")[0])
    tenant_id = str(payload.get("tid") or "")
    org_unit = str(payload.get("tenant_name") or tenant_id or "Entra")

    return {
        "sub": payload.get("sub") or email,
        "email": email,
        "name": name,
        "org_unit": org_unit,
        "tenant_id": tenant_id,
        "idp": "entra",
        "assurance_level": "idp_authenticated",
    }


def exchange_code_for_tokens(code: str, code_verifier: str, cfg: OidcConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_oidc_config()
    data: dict[str, str] = {
        "client_id": cfg.client_id,
        "scope": cfg.scopes,
        "code": code,
        "redirect_uri": cfg.redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    if cfg.client_secret:
        data["client_secret"] = cfg.client_secret

    with httpx.Client(timeout=30.0) as client:
        response = client.post(cfg.token_url(), data=data)
        if response.status_code >= 400:
            raise ValueError(f"token exchange failed: {response.status_code}")
        return response.json()


def complete_oidc_callback(
    *,
    code: str | None,
    state: str | None,
    error: str | None = None,
    error_description: str | None = None,
) -> dict[str, Any]:
    """Handle OAuth callback — exchange code, map claims, create session."""
    if error:
        reason = error_description or error
        fail_oidc_login(reason, detail={"mode": "oidc", "error": error})
        raise ValueError(reason)

    if not code or not state:
        fail_oidc_login("missing_code_or_state", detail={"mode": "oidc"})
        raise ValueError("missing authorization code or state")

    verifier = _pop_auth_state(state)
    if not verifier:
        fail_oidc_login("invalid_state", detail={"mode": "oidc"})
        raise ValueError("invalid or expired state")

    try:
        tokens = exchange_code_for_tokens(code, verifier)
        id_token = tokens.get("id_token")
        if not id_token:
            raise ValueError("token response missing id_token")
        claims = claims_from_id_token(id_token)
        return complete_oidc_login(claims)
    except ValueError as exc:
        fail_oidc_login(str(exc), detail={"mode": "oidc"})
        raise


def claims_from_mock_login(body: dict[str, Any]) -> dict[str, Any]:
    email = str(body.get("email") or body.get("actor_id") or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("email required for mock login")

    name = str(body.get("name") or body.get("actor_name") or email.split("@")[0])
    org_unit = str(body.get("org_unit") or body.get("tenant_name") or "Kommune")
    tenant_id = str(body.get("tenant_id") or body.get("tid") or "mock-tenant")

    return {
        "sub": body.get("sub") or email,
        "email": email,
        "name": name,
        "org_unit": org_unit,
        "tenant_id": tenant_id,
        "idp": body.get("idp") or "entra_mock",
        "assurance_level": "idp_authenticated",
    }


def complete_oidc_login(claims: dict[str, Any], *, session_id: str | None = None) -> dict[str, Any]:
    """Create or bind session from OIDC claims; audit success."""
    sid = create_session_from_claims(claims, session_id=session_id)
    record_auth_event("auth.login.success", {
        "session_id": sid,
        "actor_id": claims.get("email") or claims.get("sub"),
        "idp": claims.get("idp", "oidc"),
        "tenant_id": claims.get("tenant_id"),
        "assurance_level": claims.get("assurance_level", "idp_authenticated"),
    })
    return {
        "session_id": sid,
        "actor_id": claims.get("email") or claims.get("sub"),
        "actor_name": claims.get("name"),
        "org_unit": claims.get("org_unit"),
        "assurance_level": claims.get("assurance_level", "idp_authenticated"),
    }


def fail_oidc_login(reason: str, *, detail: dict | None = None) -> None:
    record_auth_event("auth.login.failure", {
        "reason": reason,
        **(detail or {}),
    })


def mock_login(body: dict[str, Any]) -> dict[str, Any]:
    cfg = load_oidc_config()
    if not cfg.mock_enabled:
        raise PermissionError("Mock login disabled — configure OIDC_CLIENT_ID for real flow")

    try:
        claims = claims_from_mock_login(body)
        return complete_oidc_login(claims, session_id=body.get("session_id"))
    except ValueError as exc:
        fail_oidc_login(str(exc), detail={"mode": "mock"})
        raise
