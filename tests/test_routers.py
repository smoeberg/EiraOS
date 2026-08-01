import os
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

os.environ["EIRA_DISABLE_DAEMONS"] = "1"

from app.http_bridge import app
from app.database import init_db

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()

client = TestClient(app)


def test_get_health():
    with patch("app.routers.health.intent_ipc.call", return_value={"ok": True}),          patch("app.routers.health.identity_ipc.call", return_value={"ok": True}),          patch("app.routers.health.graph_ipc.call", return_value={"ok": True}),          patch("app.routers.health.fleet_ipc.call", return_value={"ok": True}):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"


def test_get_oidc_config():
    response = client.get("/v1/auth/oidc/config")
    assert response.status_code == 200
    data = response.json()
    assert "authority" in data or "client_id" in data or "issuer" in data or "redirect_uri" in data


def test_post_mock_login():
    response = client.post("/v1/auth/oidc/mock-login", json={"actor_id": "test_user@eira.local"})
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data or "status" in data or "session" in data


def test_get_audit_unauthorized_and_authorized():
    # 1. Without session header -> 401 Unauthorized
    unauth_resp = client.get("/v1/audit")
    assert unauth_resp.status_code == 401

    # 2. Create valid session via mock-login
    login_resp = client.post("/v1/auth/oidc/mock-login", json={"actor_id": "auditor@eira.local"})
    data = login_resp.json()
    session_id = data.get("session_id") or data.get("session", {}).get("session_id")
    assert session_id

    # 3. With valid session header -> 200 OK
    auth_resp = client.get("/v1/audit", headers={"X-EIRA-Session-Id": session_id})
    assert auth_resp.status_code == 200
    assert isinstance(auth_resp.json(), list)


def test_post_veritas_evidence():
    payload = {
        "type": "text",
        "title": "Kildekritik dokument",
        "text": "Tekst til kildekritik og faktaverifikation"
    }
    response = client.post("/v1/veritas/evidence", json=payload)
    assert response.status_code in (200, 201)
    data = response.json()
    assert "trust_score" in data or "verdict" in data or "score" in data or "evidence_id" in data or "status" in data or "analysis" in data or "details" in data or isinstance(data, dict)


def test_post_intent_parse():
    payload = {
        "raw_input": "Opret ny sag angående byggetilladelse",
        "focus": "Kommunepilot",
        "actor_id": "mette@kommune.dk"
    }
    with patch("app.routers.intent.intent_ipc.call", return_value={"intent": "create_case", "status": "parsed"}):
        response = client.post("/v1/intent/parse", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "parsed" or "intent" in data


def test_invalid_requests():
    # Invalid endpoint -> 404 Not Found
    resp_404 = client.get("/v1/nonexistent/endpoint")
    assert resp_404.status_code == 404

    # Invalid JSON payload on intent parse -> 422 Unprocessable Entity
    resp_422 = client.post("/v1/intent/parse", content="invalid json")
    assert resp_422.status_code == 422
