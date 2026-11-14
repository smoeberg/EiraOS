"""Logout ends the session and forgets its consent key (UDVIKLINGSPLAN F1c.2,
review G-2, G-15, G-34).

Before, ``consent_keys.forget()`` had no caller: a key lived until the next
boot and a session for its full 12 hours, whatever the user did.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import consent_keys, session_store
from app.daemons.base import JsonRpcServer
from app.daemons.identityd import identity_logout, identity_session, register_identity_handlers
from app.ipc.auth import PEER_KEY

ANNE_UID, BO_UID = 1000, 1001
CLAIMS = {"sub": "anne", "identity": "did:eira:test.anne", "groups": []}


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    path = tmp_path / "eira-app.db"
    monkeypatch.setenv("EIRA_DB_PATH", str(path))
    monkeypatch.delenv("EIRA_APP_DB", raising=False)
    session_store.init_db()
    return path


def _peer(uid: int) -> SimpleNamespace:
    return SimpleNamespace(pid=os.getpid(), uid=uid, gid=uid)


def _login(uid: int = ANNE_UID) -> str:
    return session_store.create_session_from_claims(CLAIMS, os_uid=uid, logind_session="2")


def _logout(uid: int, session_id: str) -> dict:
    return identity_logout({"session_id": session_id, PEER_KEY: _peer(uid)})


def test_logout_ends_the_session_and_forgets_the_key(app_db):
    sid = _login()
    assert consent_keys.get(sid) is not None
    assert session_store.session_of_caller(ANNE_UID, sid) is not None

    assert _logout(ANNE_UID, sid) == {"ended": True}

    assert consent_keys.get(sid) is None
    assert session_store.session_of_caller(ANNE_UID, sid) is None
    who = identity_session({"session_id": sid, PEER_KEY: _peer(ANNE_UID)})
    assert who == {"session_id": None, "authenticated": False}
    gate_view = session_store.get_session_for_gate(sid)
    assert gate_view["consent_key"] is None
    ended_at = datetime.fromisoformat(gate_view["expires_at"].replace("Z", "+00:00"))
    assert ended_at <= datetime.now(timezone.utc)


def test_another_user_cannot_log_someone_out(app_db):
    sid = _login(ANNE_UID)
    assert _logout(BO_UID, sid) == {"ended": False}
    assert consent_keys.get(sid) is not None
    assert session_store.session_of_caller(ANNE_UID, sid) is not None


def test_logout_without_a_session_or_a_caller_ends_nothing(app_db):
    sid = _login()
    assert identity_logout({"session_id": sid}) == {"ended": False}
    assert _logout(ANNE_UID, "") == {"ended": False}
    assert _logout(ANNE_UID, sid) == {"ended": True}
    assert _logout(ANNE_UID, sid) == {"ended": False}  # already ended


def test_delegationd_refuses_a_session_after_logout(app_db):
    from app.daemons.delegationd import _session
    from app.gate.caller import Caller
    from app.ipc.jsonrpc import JsonRpcError

    sid = _login()
    caller = Caller(uid=ANNE_UID, pid=os.getpid(), model=False, gid=ANNE_UID)
    assert _session(caller, sid)["session_id"] == sid
    _logout(ANNE_UID, sid)
    with pytest.raises(JsonRpcError, match="ended"):
        _session(caller, sid)


def test_the_next_login_forgets_keys_of_expired_sessions(app_db):
    old = _login()
    with sqlite3.connect(app_db) as conn:
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute("UPDATE sessions SET expires_at = ? WHERE session_id = ?", (past, old))
    assert consent_keys.get(old) is not None
    new = _login()
    assert consent_keys.get(old) is None
    assert consent_keys.get(new) is not None


def test_readers_never_create_or_write_the_store(tmp_path, monkeypatch):
    """The gate and delegationd read through a read-only connection; with
    AppArmor's ``rk`` a write would be refused anyway."""
    path = tmp_path / "consent-keys.db"
    monkeypatch.setenv("EIRA_CONSENT_KEY_DB", str(path))
    assert consent_keys.get("s-1") is None
    assert not path.exists()
    consent_keys.put("s-1", "k" * 64)
    path.chmod(0o400)  # as a reader without write access sees it
    try:
        assert consent_keys.get("s-1") == "k" * 64
    finally:
        path.chmod(0o600)


def test_logout_is_a_caller_method():
    server = JsonRpcServer(name="identity-test", daemon="identityd")
    register_identity_handlers(server)
    from app.ipc.access import Access

    assert server._access["identity.logout"] is Access.CALLER
