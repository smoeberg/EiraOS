from __future__ import annotations

import json

import pytest

from app.core.cel_evaluator import CELEvaluator, CELSyntaxError
from app.core.policy_store import PolicyStore
from app.daemons.base import JsonRpcServer
from app.daemons.intentd import register_intent_handlers


def test_cel_evaluator_is_deterministic_and_rejects_python_execution() -> None:
    evaluator = CELEvaluator()
    candidate = {"payload": {"amount": 75_000, "due_date": "2026-09-01"}}
    world = {
        "actor": {"assurance_level": "org_acting"},
        "now": "2026-08-01",
    }
    assert evaluator.evaluate(
        "candidate.payload.amount <= 100000 && world.actor.assurance_level == 'org_acting'",
        candidate=candidate,
        world=world,
    )
    assert evaluator.evaluate(
        "candidate.payload.due_date >= world.now", candidate=candidate, world=world
    )
    assert evaluator.evaluate(
        "payload['amount'] == 75000", candidate=candidate, world=world
    )
    assert not evaluator.evaluate(
        "__import__('os').system('id') == 0", candidate=candidate, world=world
    )
    assert not evaluator.evaluate(
        "candidate.__class__.__mro__", candidate=candidate, world=world
    )
    assert not evaluator.evaluate(
        "candidate.payload.missing > 0", candidate=candidate, world=world
    )


def test_policy_store_versions_and_filters_rules() -> None:
    policies = PolicyStore(seed_defaults=False)
    first = policies.add_rule(
        "approve_payment", "limit", "candidate.payload.amount <= 100000", "For højt"
    )
    second = policies.update_rule(
        "approve_payment", "limit", "candidate.payload.amount <= 125000", "For højt"
    )
    policies.add_rule(
        "create_building_permit",
        "assurance",
        "world.actor.assurance_level == 'org_acting'",
        "Step-up",
    )
    active = policies.get_constraints("approve_payment")
    history = policies.get_rule_history("approve_payment", "limit")
    assert first.version == 1
    assert second.version == 2
    assert [rule.version for rule in active] == [2]
    assert [rule.version for rule in history] == [1, 2]


@pytest.mark.parametrize("method", ["intent.execute", "intent.parse", "intent.plan", "intent.confirm"])
def test_the_old_intent_methods_are_redirected_to_the_gate(method) -> None:
    """None of the old intent methods is a write path (Gate Kernel §2, F1.2):
    each answers E_GATE_REQUIRED, so an old client learns where to go."""
    server = JsonRpcServer(name="intent-test", daemon="intentd")
    register_intent_handlers(server)
    request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": method,
        "params": {"intent": "Godkend bevilling på 175.000 kr", "raw_input": "x"},
    }
    response = json.loads(server.handle_line(json.dumps(request)))
    assert response["error"]["message"] == "E_GATE_REQUIRED"
    assert response["error"]["data"]["use"] == "gate.propose"


def test_cel_rejects_python_introspection_and_import_chains() -> None:
    evaluator = CELEvaluator()
    candidate = {"payload": {"amount": 1}}
    world = {}
    hostile = [
        "candidate.__class__",
        "candidate.__class__.__subclasses__()",
        "candidate['payload'].__class__.__mro__",
        "candidate['payload']['__builtins__']['__import__']('os')",
        "__builtins__['__import__']('os')",
        "candidate['payload']['x'][0].__class__.__subclasses__()",
    ]
    for expression in hostile:
        assert evaluator.evaluate(expression, candidate=candidate, world=world) is False
        assert evaluator.last_error_flag == "cel_rejected"


def test_cel_node_budget_rejects_ten_thousand_node_expression() -> None:
    expression = " + ".join(["1"] * 5_000)
    evaluator = CELEvaluator(max_expression_length=50_000, max_nodes=128)
    with pytest.raises(CELSyntaxError) as error:
        evaluator.compile(expression)
    assert str(error.value) == "expression_too_complex"


def test_cel_large_repetition_is_rejected_without_allocating_result() -> None:
    evaluator = CELEvaluator()
    assert evaluator.evaluate("'x' * 1000000000", candidate={}, world={}) is False
    assert evaluator.last_error_flag == "cel_rejected"


def test_cel_is_deterministic_for_one_hundred_repetitions() -> None:
    evaluator = CELEvaluator()
    candidate = {"payload": {"amount": 75000, "status": "PROPOSED"}}
    world = {"limits": {"amount": 100000}, "enabled": True}
    expression = (
        "candidate.payload.amount <= world.limits.amount "
        "&& candidate.payload.status == 'PROPOSED' && world.enabled"
    )
    results = [
        evaluator.evaluate(expression, candidate=candidate, world=world)
        for _ in range(100)
    ]
    assert results == [True] * 100
    assert evaluator.last_error_flag is None


def test_cel_unexpected_exception_fails_closed_with_safe_marker() -> None:
    from collections.abc import Mapping

    class ExplodingMapping(Mapping):
        def __getitem__(self, key):
            raise RuntimeError("internal detail must not escape")

        def __iter__(self):
            return iter(())

        def __len__(self):
            return 0

    evaluator = CELEvaluator()
    assert evaluator.evaluate("candidate.payload.amount > 0", candidate=ExplodingMapping(), world={}) is False
    assert evaluator.last_error_flag == "cel_unexpected_error"


def test_cel_temporal_and_scalar_coercion_semantics() -> None:
    from datetime import date, datetime, timezone

    from app.core.cel_evaluator import _normalise_pair

    day = date(2026, 10, 19)
    midnight = datetime(2026, 10, 19, tzinfo=timezone.utc)
    assert _normalise_pair(day, midnight) == (midnight, midnight)
    assert _normalise_pair("2026-10-19", midnight) == (midnight, midnight)
    assert _normalise_pair("100000", 100000) == ("100000", 100000)
    assert _normalise_pair(None, None) == (None, None)
    assert _normalise_pair(True, 1) == (True, 1)

    evaluator = CELEvaluator()
    assert evaluator.evaluate("'100000' == 100000", candidate={}, world={}) is False
    assert evaluator.evaluate("true == 1", candidate={}, world={}) is False
    assert evaluator.evaluate("null == null", candidate={}, world={}) is True
    assert evaluator.evaluate(
        "date('2026-10-19') == timestamp('2026-10-19T00:00:00Z')",
        candidate={},
        world={},
    ) is True
