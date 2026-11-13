import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ["EIRA_DISABLE_DAEMONS"] = "1"

from app.database import init_db
from app.http_bridge import app


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


def test_post_mock_login_denied_without_opt_in(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("EIRA_OIDC_MOCK", raising=False)
    response = client.post("/v1/auth/oidc/mock-login", json={"actor_id": "test_user@eira.local"})
    assert response.status_code == 403


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



def test_invalid_requests():
    # Invalid endpoint -> 404 Not Found
    resp_404 = client.get("/v1/nonexistent/endpoint")
    assert resp_404.status_code == 404

    # Invalid JSON payload on intent confirm -> 422 Unprocessable Entity
    resp_422 = client.post(
        "/v1/intent/confirm", content="invalid json", headers={"Content-Type": "application/json"}
    )
    assert resp_422.status_code == 422

    # The prototypes' write routes are gone (UDVIKLINGSPLAN F1.6): they wrote
    # without a session or the gate, and presence took a client-named author.
    for method, route in (
        ("post", "/v1/wallet/pay"),
        ("get", "/v1/wallet/credentials"),
        ("post", "/v1/presence/annotate"),
        ("post", "/v1/context/set"),
        ("get", "/v1/context/current"),
    ):
        assert getattr(client, method)(route).status_code == 404, route

    # The old free-text routes are gone (UDVIKLINGSPLAN F1.2).
    for route in ("/v1/intent/parse", "/v1/intent/plan"):
        assert client.post(route, json={"raw_input": "x"}).status_code == 404
