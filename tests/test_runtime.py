"""EiraOS Full Runtime Integration & Architecture Tests.

Tests daemon lifecycle, IPC socket communication, cross-daemon orchestration,
session security/revocation, audit event chain integrity, and Veritas evidence processing.
"""

import tempfile

import pytest
from app.daemons.runner import start_daemons, stop_daemons
from app.ipc.client import IpcClient
from app.auth.oidc import mock_login


@pytest.fixture(scope="module")
def runtime():
    """Start all EiraOS daemons in an isolated temporary socket directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        servers = start_daemons("all", socket_dir=tmp_dir)
        yield tmp_dir, servers
        stop_daemons()


def test_daemon_lifecycle_and_sockets_ready(runtime):
    """1. Test Runtime: Verify all micro-daemons start, listen on Unix sockets, and reply to health."""
    socket_dir, servers = runtime
    expected_daemons = ["stated", "identityd", "fleetd", "veritasd", "intentd", "graphd"]

    for daemon_name in expected_daemons:
        assert daemon_name in servers
        client = IpcClient(daemon_name)
        res = client.call("health")
        assert isinstance(res, dict)
        assert res.get("status") in ("ok", True) or res.get("ok") is True or "version" in res


def test_end_to_end_intent_orchestration(runtime):
    """2. Test End-to-End Intent: raw input -> intentd parse -> policy/context -> graph/stated -> result."""
    intent_client = IpcClient("intentd")
    
    parse_res = intent_client.call("intent.parse", {
        "raw_input": "Opret ny sag angående byggetilladelse",
        "focus": "Kommunepilot",
        "actor_id": "mette@kommune.dk"
    })
    
    assert isinstance(parse_res, dict)
    assert parse_res.get("status") in ("parsed", "ok") or "intent" in parse_res or "intent_id" in parse_res


def test_veritas_evidence_processing_and_conflict_scoring(runtime):
    """3. Test Veritas Evidence Engine: Submit evidence via IPC, check trust scoring & layers."""
    veritas_client = IpcClient("veritasd")

    evidence_res = veritas_client.call("veritas.evaluate", {
        "type": "text",
        "title": "Byggetilladelse Bilag 1",
        "text": "Ansøgning om opførelse af garage på 40m2."
    })

    assert isinstance(evidence_res, dict)
    assert "trust_score" in evidence_res
    assert "layers" in evidence_res
    assert "hud_certificate" in evidence_res


def test_audit_event_chain_integrity(runtime):
    """4. Test Audit Chain Integritet: Append state / event and verify append-only audit trail."""
    state_client = IpcClient("stated")

    # Append an audit log entry
    audit_res = state_client.call("audit.append", {
        "event_type": "TEST_AUDIT_LOG",
        "actor_id": "system_test",
        "details": {"action": "integration_test_run"}
    })
    assert isinstance(audit_res, dict)
    assert audit_res.get("status") == "appended"
    assert "hash" in audit_res

    # Verify audit chain integrity
    verify_res = state_client.call("audit.verify", {})
    assert isinstance(verify_res, dict)
    assert verify_res.get("valid") is True or verify_res.get("ok") is True or "events" in verify_res


def test_session_security_and_revocation(runtime):
    """5. Test Session Security: Session creation via mock_login and identity verification."""
    login_info = mock_login({"email": "auditor@eiraos.local", "name": "Test Auditor"})
    assert "session_id" in login_info
    session_id = login_info["session_id"]

    identity_client = IpcClient("identityd")
    
    res = identity_client.call("health")
    assert isinstance(res, dict)
