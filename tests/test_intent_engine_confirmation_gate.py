from __future__ import annotations

import pytest

from app.daemons import intent_engine
from app.ipc.jsonrpc import JsonRpcError


@pytest.mark.parametrize(
    ("plan_fields", "expected_message"),
    [
        (
            {"can_execute": False, "block_reason": "Capability mangler"},
            "Capability mangler",
        ),
        (
            {"can_execute": False, "block_reason": None},
            "Planen tillader ikke, at handlingen udføres",
        ),
        ({}, "Planen tillader ikke, at handlingen udføres"),
        (
            {"can_execute": None, "block_reason": "Uafklaret plan"},
            "Uafklaret plan",
        ),
    ],
)
def test_intent_confirm_fails_closed_when_plan_does_not_allow_execution(
    monkeypatch, plan_fields, expected_message
):
    pending = {
        "intent_id": "intent-1",
        "status": "pending_confirmation",
        "required_assurance": "org_acting",
        # Both are intentionally present: neither can override a blocked plan.
        "capability_match": {"adapter_id": "adapter-1"},
        **plan_fields,
    }
    monkeypatch.setattr(intent_engine, "get_pending", lambda *_: pending)
    monkeypatch.setattr(
        intent_engine,
        "get_session",
        lambda *_: {"assurance_level": "org_acting"},
    )

    def must_not_execute(_pending):
        pytest.fail("executor must not be called when the plan does not allow execution")

    monkeypatch.setattr(intent_engine, "execute_intent", must_not_execute)

    with pytest.raises(JsonRpcError) as raised:
        intent_engine.intent_confirm({"intent_id": "intent-1", "session_id": "session-1"})

    assert raised.value.code == -32002
    assert raised.value.message == "cannot_execute"
    assert raised.value.data["user_message"] == expected_message


@pytest.mark.parametrize(
    ("session", "required_assurance", "expected_code", "expected_message"),
    [
        (
            None,
            None,
            -32002,
            "Sessionen findes ikke længere — planlæg handlingen igen",
        ),
        (
            {"assurance_level": "eid_low"},
            "eid_high",
            -32001,
            "Handlingen kræver assurance-niveauet eid_high",
        ),
    ],
)
def test_intent_confirm_rechecks_session_and_assurance(
    monkeypatch, session, required_assurance, expected_code, expected_message
):
    pending = {
        "intent_id": "intent-2",
        "status": "pending_confirmation",
        "can_execute": True,
        "required_assurance": required_assurance,
        "capability_match": {
            "adapter_id": "adapter-1",
            "required_assurance": required_assurance,
        },
    }
    monkeypatch.setattr(intent_engine, "get_pending", lambda *_: pending)
    monkeypatch.setattr(intent_engine, "get_session", lambda *_: session)

    def must_not_execute(_pending):
        pytest.fail("executor must not run without a valid session and sufficient assurance")

    monkeypatch.setattr(intent_engine, "execute_intent", must_not_execute)

    with pytest.raises(JsonRpcError) as raised:
        intent_engine.intent_confirm({"intent_id": "intent-2", "session_id": "session-2"})

    assert raised.value.code == expected_code
    assert raised.value.data["user_message"] == expected_message
