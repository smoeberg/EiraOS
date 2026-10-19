from __future__ import annotations

import sqlite3

import pytest

from app.core.event import EventBus
from app.core.knowledge import KnowledgeRepository
from app.core.policy_store import PolicyDefinition, PolicyStore
from app.daemons.intentd import IntentDaemonService
from app.intent_parser import IntentParser
from app.ipc.jsonrpc import CONSTRAINT_VIOLATION, JsonRpcError


class RecordingAppender:
    def __init__(self) -> None:
        self.states = []

    def append(self, state) -> None:
        self.states.append(state)


class CrashingPolicyStore:
    def get_constraints(self, transformation_type: str):
        raise RuntimeError("secret database details must never cross IPC")


def _service(policy_store, appender):
    return IntentDaemonService(
        parser=IntentParser(),
        policy_store=policy_store,
        state_store=appender,
        event_bus=EventBus(),
        knowledge_repository=KnowledgeRepository(),
    )


def _params():
    return {
        "intent": "Godkend udbetaling 500 kr",
        "assurance_level": "org_acting",
        "actor_id": "actor-1",
    }


def test_intent_execute_happy_path_appends_only_after_constraints_pass():
    policies = PolicyStore(seed_defaults=False)
    policies.add_rule(
        "approve_payment",
        "amount_limit",
        "candidate.payload.amount <= 100000",
        "Beløbet er for højt.",
    )
    policies.add_rule(
        "approve_payment",
        "assurance",
        "world.actor.assurance_level == 'org_acting'",
        "Der kræves organisationsgodkendelse.",
    )
    appender = RecordingAppender()

    result = _service(policies, appender).execute(_params())

    assert result["status"] == "executed"
    assert len(result["applied_constraints"]) == 2
    assert len(appender.states) == 1
    assert appender.states[0].hash == result["state"]["hash"]


def test_intent_execute_rejects_false_constraint_without_appending():
    policies = PolicyStore(seed_defaults=False)
    policies.add_rule(
        "approve_payment",
        "always_reject",
        "candidate.payload.amount < 1",
        "Denne udbetaling er afvist.",
    )
    appender = RecordingAppender()

    with pytest.raises(JsonRpcError) as raised:
        _service(policies, appender).execute(_params())

    assert raised.value.code == CONSTRAINT_VIOLATION
    assert raised.value.message == "CONSTRAINT_VIOLATION"
    assert raised.value.data["rule_id"] == "always_reject"
    assert raised.value.data["user_message"] == "Denne udbetaling er afvist."
    assert raised.value.data["rationale"]
    assert appender.states == []


def test_intent_execute_policy_store_crash_fails_closed_without_ipc_traceback():
    appender = RecordingAppender()

    with pytest.raises(JsonRpcError) as raised:
        _service(CrashingPolicyStore(), appender).execute(_params())

    assert raised.value.code == -32603
    assert raised.value.message == "INTENT_EXECUTION_FAILED"
    assert "secret database details" not in repr(raised.value.data)
    assert "RuntimeError" not in repr(raised.value.data)
    assert raised.value.data["user_message"]
    assert appender.states == []


def test_policy_seed_is_idempotent_and_rule_updates_create_immutable_history():
    policies = PolicyStore(seed_defaults=False)
    original = PolicyDefinition(
        "approve_payment", "amount_limit", "candidate.payload.amount <= 100000",
        "Beløbet er for højt.", {"limit": 100000},
    )
    policies.seed([original])
    policies.seed([
        PolicyDefinition(
            "approve_payment", "amount_limit", "candidate.payload.amount <= 1",
            "Forsøg på at ændre den seedede regel.",
        )
    ])

    history = policies.get_rule_history("approve_payment", "amount_limit")
    assert len(history) == 1
    assert history[0].expression == original.expression
    row = policies._connection.execute(
        "SELECT content_hash FROM policy_rules WHERE transformation_type = ? AND rule_id = ? AND version = 1",
        ("approve_payment", "amount_limit"),
    ).fetchone()
    assert len(row["content_hash"]) == 64

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        policies._connection.execute(
            "UPDATE policy_rules SET expression = ? WHERE transformation_type = ? AND rule_id = ? AND version = 1",
            ("true", "approve_payment", "amount_limit"),
        )

    policies.add_rule(
        "approve_payment", "amount_limit", "candidate.payload.amount <= 1",
        "Ny version med ændret grænse.",
    )
    history = policies.get_rule_history("approve_payment", "amount_limit")
    assert [rule.version for rule in history] == [1, 2]
    assert history[0].expression == original.expression
    assert history[1].expression == "candidate.payload.amount <= 1"
    hashes = policies._connection.execute(
        "SELECT content_hash FROM policy_rules WHERE transformation_type = ? AND rule_id = ? ORDER BY version",
        ("approve_payment", "amount_limit"),
    ).fetchall()
    assert hashes[0]["content_hash"] != hashes[1]["content_hash"]


def test_policy_store_detects_rule_hash_tampering():
    policies = PolicyStore(seed_defaults=False)
    policies.add_rule(
        "approve_payment", "amount_limit", "candidate.payload.amount <= 100000",
        "Beløbet er for højt.",
    )
    policies._connection.execute("DROP TRIGGER policy_rules_immutable_update")
    policies._connection.execute(
        "UPDATE policy_rules SET expression = ? WHERE transformation_type = ? AND rule_id = ?",
        ("true", "approve_payment", "amount_limit"),
    )

    with pytest.raises(ValueError, match="policy_rule_integrity_check_failed"):
        policies.get_constraints("approve_payment")
