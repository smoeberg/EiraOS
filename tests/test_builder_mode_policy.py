"""Builder Mode is policy-gated; a client cannot grant it to itself."""

import pytest

from app.daemons import intent_engine
from app.ipc.jsonrpc import JsonRpcError


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "db_path", tmp_path / "eira.db")
    from app.database import init_db

    init_db()


def test_builder_denied_without_policy_even_if_client_claims_permission(monkeypatch):
    monkeypatch.delenv("EIRA_BUILDER_MODE_ALLOWED", raising=False)
    with pytest.raises(JsonRpcError) as exc:
        intent_engine.presentation_mode_set(
            {"session_id": "s-1", "mode": "builder", "policy_allowed": True}
        )
    assert exc.value.code == -32003
    assert intent_engine.presentation_mode_get({"session_id": "s-1"})["mode"] != "builder"


def test_builder_allowed_by_policy(monkeypatch):
    monkeypatch.setenv("EIRA_BUILDER_MODE_ALLOWED", "1")
    result = intent_engine.presentation_mode_set({"session_id": "s-2", "mode": "builder"})
    assert result["mode"] == "builder"
    assert intent_engine.presentation_mode_get({"session_id": "s-2"})["mode"] == "builder"


def test_revoked_policy_falls_back_to_explorer(monkeypatch):
    monkeypatch.setenv("EIRA_BUILDER_MODE_ALLOWED", "1")
    intent_engine.presentation_mode_set({"session_id": "s-3", "mode": "builder"})
    monkeypatch.delenv("EIRA_BUILDER_MODE_ALLOWED")
    state = intent_engine.presentation_mode_get({"session_id": "s-3"})
    assert state["mode"] == "explorer"
    assert state["builder_allowed"] is False


def test_explorer_always_allowed(monkeypatch):
    monkeypatch.delenv("EIRA_BUILDER_MODE_ALLOWED", raising=False)
    assert intent_engine.presentation_mode_set({"session_id": "s-4", "mode": "explorer"})["mode"] == "explorer"
