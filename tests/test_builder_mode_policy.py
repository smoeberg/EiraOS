"""Builder Mode is policy-gated; a client cannot grant it to itself.

The mode belongs to the OS user on the socket (SO_PEERCRED), not to a session
a client names (UDVIKLINGSPLAN F1.5, fundregister S-4/S-5): the terminal's
own check sees the mode the UI switched to, and nobody gets a session by
naming an actor.
"""

import sqlite3
from types import SimpleNamespace

import pytest

from app.daemons import identityd, intent_engine
from app.ipc.auth import PEER_KEY
from app.ipc.jsonrpc import JsonRpcError

ANNE, BO = 1000, 1001


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "db_path", tmp_path / "eira.db")
    # session_store resolves its own path from the environment.
    monkeypatch.setenv("EIRA_DB_PATH", str(tmp_path / "eira.db"))
    monkeypatch.delenv("EIRA_APP_DB", raising=False)
    from app.database import init_db

    init_db()


def as_user(uid, **params):
    return {**params, PEER_KEY: SimpleNamespace(uid=uid, gid=uid, pid=4242)}


def sessions() -> int:
    from app.session_store import get_db_path

    with sqlite3.connect(get_db_path()) as conn:
        return conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]


def test_builder_denied_without_policy_even_if_client_claims_permission(monkeypatch):
    monkeypatch.delenv("EIRA_BUILDER_MODE_ALLOWED", raising=False)
    with pytest.raises(JsonRpcError) as exc:
        intent_engine.presentation_mode_set(as_user(ANNE, mode="builder", policy_allowed=True))
    assert exc.value.code == -32003
    assert intent_engine.presentation_mode_get(as_user(ANNE))["mode"] != "builder"


def test_builder_allowed_by_policy(monkeypatch):
    monkeypatch.setenv("EIRA_BUILDER_MODE_ALLOWED", "1")
    assert intent_engine.presentation_mode_set(as_user(ANNE, mode="builder"))["mode"] == "builder"
    assert intent_engine.presentation_mode_get(as_user(ANNE))["mode"] == "builder"


def test_the_terminal_check_sees_the_mode_the_ui_set(monkeypatch):
    """S-4: the UI and the Tauri backend both ask without a session id; both
    are the same OS user, so both see Builder."""
    monkeypatch.setenv("EIRA_BUILDER_MODE_ALLOWED", "1")
    intent_engine.presentation_mode_set(as_user(ANNE, mode="builder"))
    ui = intent_engine.presentation_mode_get(as_user(ANNE))
    terminal = intent_engine.presentation_mode_get(as_user(ANNE))
    assert ui["mode"] == terminal["mode"] == "builder"


def test_one_users_mode_is_not_anothers(monkeypatch):
    monkeypatch.setenv("EIRA_BUILDER_MODE_ALLOWED", "1")
    intent_engine.presentation_mode_set(as_user(ANNE, mode="builder"))
    assert intent_engine.presentation_mode_get(as_user(BO))["mode"] == "explorer"


def test_a_named_session_does_not_choose_the_mode(monkeypatch):
    monkeypatch.setenv("EIRA_BUILDER_MODE_ALLOWED", "1")
    intent_engine.presentation_mode_set(as_user(ANNE, mode="builder", session_id="bo-session"))
    assert intent_engine.presentation_mode_get(as_user(BO, session_id="bo-session"))["mode"] == "explorer"


def test_the_mode_cannot_be_set_outside_a_socket(monkeypatch):
    monkeypatch.setenv("EIRA_BUILDER_MODE_ALLOWED", "1")
    with pytest.raises(JsonRpcError):
        intent_engine.presentation_mode_set({"mode": "builder"})


def test_revoked_policy_falls_back_to_explorer(monkeypatch):
    monkeypatch.setenv("EIRA_BUILDER_MODE_ALLOWED", "1")
    intent_engine.presentation_mode_set(as_user(ANNE, mode="builder"))
    monkeypatch.delenv("EIRA_BUILDER_MODE_ALLOWED")
    state = intent_engine.presentation_mode_get(as_user(ANNE))
    assert state["mode"] == "explorer"
    assert state["builder_allowed"] is False


def test_explorer_always_allowed(monkeypatch):
    monkeypatch.delenv("EIRA_BUILDER_MODE_ALLOWED", raising=False)
    assert intent_engine.presentation_mode_set(as_user(ANNE, mode="explorer"))["mode"] == "explorer"


def test_reading_the_mode_or_the_dashboard_creates_no_session():
    """S-5: before F1.5 every call without a session id created one."""
    intent_engine.presentation_mode_get(as_user(ANNE))
    intent_engine.dashboard_get(as_user(ANNE, actor_id="mette@kommune.dk"))
    identityd.identity_session(as_user(ANNE, actor_id="mette@kommune.dk"))
    assert sessions() == 0


def test_the_dashboard_does_not_echo_a_claimed_identity():
    dash = intent_engine.dashboard_get(as_user(ANNE, actor_id="mette@kommune.dk"))
    assert dash["actor_id"] is None
    assert dash["authenticated"] is False
    assert "mette" not in dash["greeting"]


def _authenticated(uid, sid):
    from app.session_store import create_session_from_claims

    return create_session_from_claims(
        {"sub": f"user-{uid}", "name": f"User {uid}", "groups": []},
        os_uid=uid, session_id=sid,
    )


def test_identity_session_returns_only_the_callers_own_session():
    anne = _authenticated(ANNE, "anne-1")
    assert identityd.identity_session(as_user(ANNE))["session_id"] == anne
    assert identityd.identity_session(as_user(ANNE, session_id=anne))["authenticated"] is True
    # Bo names Anne's session: he gets nothing, not her session.
    assert identityd.identity_session(as_user(BO, session_id=anne)) == {
        "session_id": None, "authenticated": False}


def test_identity_session_never_returns_secrets():
    _authenticated(ANNE, "anne-2")
    session = identityd.identity_session(as_user(ANNE))
    assert "consent_key" not in session
