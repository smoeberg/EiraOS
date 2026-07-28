import pytest
from fastapi.testclient import TestClient
from app.http_bridge import app
from app.daemons.runner import start_daemons

@pytest.fixture(autouse=True)
def init_daemons():
    start_daemons()

def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "daemons" in data

def test_oidc_config_endpoint():
    with TestClient(app) as client:
        response = client.get("/v1/auth/oidc/config")
        assert response.status_code == 200
        data = response.json()
        assert "issuer" in data

def test_audit_endpoint():
    with TestClient(app) as client:
        response = client.get("/v1/audit")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

def test_audit_append_only_enforcement():
    with TestClient(app) as client:
        response = client.delete("/v1/audit/some_event_id")
        assert response.status_code == 405
        assert "append-only" in response.json()["detail"]
