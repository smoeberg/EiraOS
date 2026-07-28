"""Contract acceptance tests — CP-OIDC-001 Enterprise SSO."""

from __future__ import annotations

import base64
import json
import uuid
from unittest.mock import patch

import pytest

from app.auth.oidc import (
    claims_from_id_token,
    complete_oidc_callback,
    load_oidc_config,
    mock_login,
    start_oidc_login,
)
from app.database import get_connection, init_db
from app.daemons import identityd
from app.session_store import ensure_session, get_session


@pytest.fixture(autouse=True)
def _db():
    init_db()
    yield


def _fake_id_token(*, email: str = "live@kommune.dk", name: str = "Live Bruger", tid: str = "entra-live") -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({
            "sub": "sub-live",
            "preferred_username": email,
            "name": name,
            "tid": tid,
        }).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.sig"


def test_cp_oidc_mock_login_creates_session_and_audit():
    result = mock_login({
        "email": "sso@kommune.dk",
        "name": "SSO Bruger",
        "org_unit": "Skoleforvaltningen",
        "tenant_id": "entra-tenant-abc",
    })
    assert result["session_id"]
    assert result["actor_id"] == "sso@kommune.dk"
    assert result["assurance_level"] == "idp_authenticated"

    session = get_session(result["session_id"])
    assert session["actor_name"] == "SSO Bruger"
    assert session["org_unit"] == "Skoleforvaltningen"

    with get_connection() as conn:
        row = conn.execute(
            "SELECT event_type, payload FROM audit_events WHERE event_type = ? ORDER BY created_at DESC LIMIT 1",
            ("auth.login.success",),
        ).fetchone()
    assert row is not None
    payload = json.loads(row["payload"])
    assert payload["actor_id"] == "sso@kommune.dk"
    assert "id_token" not in payload


def test_cp_oidc_login_failure_audited():
    from app.auth.oidc import fail_oidc_login

    fail_oidc_login("invalid_email", detail={"mode": "mock"})
    with get_connection() as conn:
        row = conn.execute(
            "SELECT event_type FROM audit_events WHERE event_type = ?",
            ("auth.login.failure",),
        ).fetchone()
    assert row is not None


def test_cp_oidc_mock_login_missing_email():
    with pytest.raises(ValueError):
        mock_login({"name": "No Email"})


def test_cp_oidc_session_isolation_after_sso():
    """OIDC session + step-up — B unaffected (CP-SESSION-001 + OIDC)."""
    login_a = mock_login({"email": "a@kommune.dk", "name": "A"})
    sid_b = ensure_session(str(uuid.uuid4()), "b@kommune.dk")

    identityd.identity_step_up({"session_id": login_a["session_id"]})

    assert get_session(login_a["session_id"])["assurance_level"] == "org_acting"
    assert get_session(sid_b)["assurance_level"] == "eid_low"


def test_cp_oidc_live_config_when_client_id_set(monkeypatch):
    monkeypatch.setenv("OIDC_CLIENT_ID", "app-client-id")
    monkeypatch.setenv("OIDC_TENANT_ID", "tenant-abc")
    monkeypatch.setenv("EIRA_OIDC_MOCK", "false")

    cfg = load_oidc_config()
    assert cfg.mock_enabled is False
    assert cfg.client_id == "app-client-id"
    assert "login.microsoftonline.com/tenant-abc" in cfg.authorize_url()


def test_cp_oidc_start_login_builds_entra_url(monkeypatch):
    monkeypatch.setenv("OIDC_CLIENT_ID", "app-client-id")
    monkeypatch.setenv("OIDC_TENANT_ID", "tenant-abc")
    monkeypatch.setenv("EIRA_OIDC_MOCK", "false")

    result = start_oidc_login()
    assert "login.microsoftonline.com/tenant-abc/oauth2/v2.0/authorize" in result["authorize_url"]
    assert "code_challenge=" in result["authorize_url"]
    assert "state=" in result["authorize_url"]


def test_cp_oidc_callback_exchanges_code(monkeypatch):
    monkeypatch.setenv("OIDC_CLIENT_ID", "app-client-id")
    monkeypatch.setenv("OIDC_TENANT_ID", "tenant-abc")
    monkeypatch.setenv("EIRA_OIDC_MOCK", "false")

    login = start_oidc_login()
    state = login["state"]
    # Extract state from URL for robustness
    assert state

    id_token = _fake_id_token()
    with patch("app.auth.oidc.exchange_code_for_tokens") as exchange:
        exchange.return_value = {"id_token": id_token, "access_token": "at"}
        result = complete_oidc_callback(code="auth-code", state=state)

    assert result["actor_id"] == "live@kommune.dk"
    assert result["session_id"]
    exchange.assert_called_once()


def test_cp_oidc_claims_from_id_token():
    claims = claims_from_id_token(_fake_id_token(email="x@y.dk", name="X Y"))
    assert claims["email"] == "x@y.dk"
    assert claims["name"] == "X Y"
    assert claims["idp"] == "entra"
    assert claims["assurance_level"] == "idp_authenticated"


def test_cp_oidc_callback_invalid_state(monkeypatch):
    monkeypatch.setenv("OIDC_CLIENT_ID", "app-client-id")
    monkeypatch.setenv("EIRA_OIDC_MOCK", "false")

    with pytest.raises(ValueError, match="invalid or expired state"):
        complete_oidc_callback(code="code", state="not-stored")
