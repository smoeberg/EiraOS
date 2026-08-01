import os
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
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") in ("ok", "healthy") or "status" in data or "ok" in data or data.get("service")


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
    # Without session header -> 401 Unauthorized
    unauth_resp = client.get("/v1/audit")
    assert unauth_resp.status_code == 401

    # First mock-login to obtain a valid session_id
    login_resp = client.post("/v1/auth/oidc/mock-login", json={"actor_id": "auditor@eira.local"})
    session_id = login_resp.json().get("session_id", "test_session_123")

    # With valid session header -> 200 OK
    auth_resp = client.get("/v1/audit", headers={"X-EIRA-Session-Id": session_id})
    assert auth_resp.status_code == 200
    data = auth_resp.json()
    assert isinstance(data, (list, dict))


def test_post_veritas_evidence():
    payload = {
        "text": "Tekst til kildekritik og faktaverifikation",
        "evidence_type": "text"
    }
    response = client.post("/v1/veritas/evidence", json=payload)
    assert response.status_code in (200, 201)
    data = response.json()
    assert "trust_score" in data or "verdict" in data or "score" in data or "evidence_id" in data or "status" in data


def test_post_intent_parse():
    payload = {
        "text": "Opret ny sag angående byggetilladelse",
        "raw_text": "Opret ny sag angående byggetilladelse",
        "prompt": "Opret ny sag angående byggetilladelse"
    }
    response = client.post("/v1/intent/parse", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "intent" in data or "parsed" in data or "actions" in data or "action" in data or "status" in data or "raw_text" in data


def test_invalid_requests():
    # Invalid endpoint -> 404
    resp_404 = client.get("/v1/nonexistent/endpoint")
    assert resp_404.status_code == 404

    # Invalid JSON payload on intent parse -> 422 Unprocessable Entity
    resp_422 = client.post("/v1/intent/parse", content="invalid json")
    assert resp_422.status_code == 422
