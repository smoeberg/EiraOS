from __future__ import annotations

import pytest

from app import database
from app.daemons import intent_engine
from app.ipc.jsonrpc import JsonRpcError
from app.pending_intents import get_pending, save_pending
from app.session_store import ensure_session


@pytest.fixture
def intent_db(tmp_path, monkeypatch):
    db_path = tmp_path / "intent-confirm.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    monkeypatch.setenv("EIRA_DB_PATH", str(db_path))
    database.init_db()
    session_id = ensure_session(
        "session-a", "actor-a", assurance_level="org_acting"
    )
    return session_id


def _payload(intent_id: str, **overrides) -> dict:
    payload = {
        "intent_id": intent_id,
        "status": "pending_confirmation",
        "action": "approve",
        "resource": "document",
        "required_assurance": "org_acting",
        "can_execute": True,
        "block_reason": None,
        "capability_match": {
            "adapter_id": "adapter-a",
            "adapter_name": "Adapter A",
            "action": "approve",
            "resource": "document",
        },
    }
    payload.update(overrides)
    return payload


def test_confirm_cannot_override_negative_plan(intent_db, monkeypatch):
    intent_id = "intent-blocked"
    save_pending(
        intent_db,
        intent_id,
        _payload(intent_id, can_execute=False, block_reason="Planner blocked it"),
    )

    def should_not_execute(_pending):
        pytest.fail("blocked intent must not reach executor")

    monkeypatch.setattr(intent_engine, "execute_intent", should_not_execute)

    with pytest.raises(JsonRpcError, match="cannot_execute"):
        intent_engine.intent_confirm(
            {"session_id": intent_db, "intent_id": intent_id}
        )

    assert get_pending(intent_id, intent_db) is not None


def test_confirm_enforces_any_required_assurance(intent_db, monkeypatch):
    intent_id = "intent-high-assurance"
    save_pending(
        intent_db,
        intent_id,
        _payload(intent_id, required_assurance="eid_high"),
    )
    monkeypatch.setattr(
        intent_engine,
        "execute_intent",
        lambda _pending: pytest.fail("assurance failure must block execution"),
    )

    with pytest.raises(JsonRpcError, match="assurance_required"):
        intent_engine.intent_confirm(
            {"session_id": intent_db, "intent_id": intent_id}
        )


def test_confirm_is_single_claim_and_keeps_idempotency_record(
    intent_db, monkeypatch
):
    intent_id = "intent-once"
    save_pending(intent_db, intent_id, _payload(intent_id, required_assurance=None))
    calls = []

    def fake_execute(pending):
        calls.append(pending["intent_id"])
        return {"message": "stub executed", "status": "executed_stub"}

    monkeypatch.setattr(intent_engine, "execute_intent", fake_execute)

    result = intent_engine.intent_confirm(
        {"session_id": intent_db, "intent_id": intent_id}
    )
    assert result["status"] == "executed"

    with pytest.raises(JsonRpcError, match="intent_not_pending"):
        intent_engine.intent_confirm(
            {"session_id": intent_db, "intent_id": intent_id}
        )

    assert calls == [intent_id]
    with database.get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM pending_intents WHERE intent_id = ?",
            (intent_id,),
        ).fetchone()
    assert row["status"] == "executed"
