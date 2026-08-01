from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.core.audit import StateAuditTrail
from app.core.state import State
from app.core.store import StateStore
from app.daemons import stated
from app.daemons.base import JsonRpcServer, MAX_REQUEST_BYTES
from app.ipc import auth
from app.ipc.jsonrpc import JsonRpcError
from app.ipc.socket_security import (
    PeerCredentialError,
    PeerCredentials,
    validate_peer_credentials,
)


def test_ipc_token_uses_constant_time_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIRA_IPC_TOKEN", "a" * 64)
    calls: list[tuple[bytes, bytes]] = []

    def compare(left: bytes, right: bytes) -> bool:
        calls.append((left, right))
        return left == right

    monkeypatch.setattr(auth.hmac, "compare_digest", compare)
    with pytest.raises(JsonRpcError) as rejected:
        auth.strip_and_validate_ipc_auth(
            {"_eira": {"ipc_token": "a" * 63 + "b"}}
        )
    assert rejected.value.code == auth.AUTH_FAILED
    assert calls == [(b"a" * 63 + b"b", b"a" * 64)]


def test_sha3_forgery_is_rejected_before_state_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    store = StateStore(":memory:")
    monkeypatch.setattr(stated, "_store", store)
    valid = State(type="AuditProbe", payload={"approved": True})
    forged = valid.model_dump(mode="json")
    forged["payload"] = {"approved": False}
    with pytest.raises(JsonRpcError):
        stated.state_append(forged)
    assert store.count() == 0


def test_unapproved_peer_credentials_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.ipc.socket_security.get_peer_credentials",
        lambda _connection: PeerCredentials(pid=999_999, uid=90_001, gid=90_002),
    )
    monkeypatch.setattr("app.ipc.socket_security._supplementary_gids", lambda _pid: set())
    with pytest.raises(PeerCredentialError):
        validate_peer_credentials(
            object(),  # type: ignore[arg-type]
            allowed_uids={1000},
            allowed_gids={1000},
        )


def test_json_rpc_rejects_oversized_and_non_object_requests() -> None:
    server = JsonRpcServer("security-test", "stated")
    server.register("health", lambda _: {"ok": True})
    oversized = server.handle_line("x" * (MAX_REQUEST_BYTES + 1))
    assert json.loads(oversized)["error"]["message"] == "Request too large"
    non_object = server.handle_line("[]")
    assert json.loads(non_object)["error"]["message"] == "Request must be a JSON object"


def test_audit_chain_detects_historical_payload_tampering(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    store = StateStore(str(database))
    trail = StateAuditTrail(store)
    first = trail.append("pilot.started", {"pilot": "A"}, actor_id="operator")
    trail.append("pilot.approved", {"approved": True}, actor_id="reviewer")
    assert trail.verify().valid is True

    connection = store._get_conn()  # security test intentionally bypasses API
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "UPDATE states SET payload = ? WHERE id = ?",
            ('{"actor_id":"attacker"}', str(first.id)),
        )
    connection.execute("DROP TRIGGER states_append_only_update")
    connection.execute(
        "UPDATE states SET payload = ? WHERE id = ?",
        ('{"actor_id":"attacker"}', str(first.id)),
    )
    connection.commit()
    connection.close()
    result = trail.verify()
    assert result.valid is False
    assert "event_1:state_hash_invalid" in result.errors
