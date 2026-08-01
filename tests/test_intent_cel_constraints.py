from __future__ import annotations

import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.cel_evaluator import CELEvaluator
from app.core.event import EventBus
from app.core.knowledge import KnowledgeRepository
from app.core.policy_store import PolicyStore
from app.core.store import StateStore
from app.daemons.base import JsonRpcServer
from app.daemons.intentd import IntentDaemonService, register_intent_handlers
from app.intent_parser import IntentParser
from app.ipc.jsonrpc import CONSTRAINT_VIOLATION, JsonRpcError


def _service():
    store = StateStore(":memory:")
    bus = EventBus()
    knowledge = KnowledgeRepository()
    service = IntentDaemonService(
        parser=IntentParser(),
        policy_store=PolicyStore(),
        state_store=store,
        event_bus=bus,
        knowledge_repository=knowledge,
    )
    return service, store, bus, knowledge


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


def test_intent_parser_creates_immutable_hashed_proposal() -> None:
    proposal = IntentParser().parse("Opret byggetilladelse for Bygaden 12")
    assert proposal.suggested_transformation == "create_building_permit"
    assert proposal.candidate_state.payload["address"] == "Bygaden 12"
    assert proposal.candidate_state.hash == proposal.candidate_state.compute_hash()
    assert 0.0 <= proposal.confidence_score <= 1.0
    with pytest.raises(ValidationError):
        proposal.rationale = "ændret"


def test_intent_parser_accepts_validated_mistral_structure() -> None:
    parser = IntentParser(
        lambda _: {
            "suggested_transformation": "create_building_permit",
            "state_type": "BuildingPermitState",
            "payload": {"address": "AI Vej 7", "status": "PROPOSED"},
            "confidence_score": 0.88,
            "rationale": "Struktureret af lokal Mistral.",
        },
        source_model="mistral",
    )
    proposal = parser.parse("Opret sagen")
    assert proposal.source_model == "mistral"
    assert proposal.candidate_state.payload["address"] == "AI Vej 7"


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


def test_intent_execution_success() -> None:
    service, store, bus, knowledge = _service()
    result = service.execute(
        {
            "intent": "Opret byggetilladelse for Bygaden 12",
            "world": {"actor": {"id": "caseworker-1", "assurance_level": "org_acting"}},
        }
    )
    state_id = result["state"]["id"]
    assert result["status"] == "executed"
    assert store.count() == 1
    assert len(bus.get_audit_log()) == 1
    proofs = knowledge.get_proofs_for_state(UUID(state_id))
    assert len(proofs) == 1
    assert proofs[0].proof_type == "CEL_CONSTRAINT"


def test_intent_execution_blocked_by_cel() -> None:
    service, store, bus, knowledge = _service()
    with pytest.raises(JsonRpcError) as error:
        service.execute(
            {
                "intent": "Godkend bevilling på 150.000 kr",
                "world": {
                    "actor": {"id": "caseworker-1", "assurance_level": "org_acting"}
                },
            }
        )
    assert error.value.code == CONSTRAINT_VIOLATION
    assert error.value.message == "CONSTRAINT_VIOLATION"
    assert "candidate.payload.amount <= 100000" == error.value.data["rule"]
    assert store.count() == 0
    assert bus.get_audit_log() == []
    assert knowledge._entries == []


def test_intent_step_up_escalation() -> None:
    service, store, _, _ = _service()
    with pytest.raises(JsonRpcError) as error:
        service.execute(
            {
                "intent": "Opret byggetilladelse for Bygaden 12",
                "world": {
                    "actor": {"id": "caseworker-1", "assurance_level": "eid_low"}
                },
            }
        )
    assert error.value.code == CONSTRAINT_VIOLATION
    assert error.value.data["step_up_required"] is True
    assert error.value.data["required_assurance"] == "org_acting"
    assert error.value.data["step_up_method"] == "mitid_erhverv"
    assert store.count() == 0


def test_intent_execute_jsonrpc_contract_does_not_persist_rejection() -> None:
    service, store, _, _ = _service()
    server = JsonRpcServer(name="intent-test", daemon="intentd")
    register_intent_handlers(server, service)
    request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "intent.execute",
        "params": {
            "intent": "Godkend bevilling på 175.000 kr",
            "world": {"actor": {"id": "caseworker", "assurance_level": "org_acting"}},
        },
    }
    response = json.loads(server.handle_line(json.dumps(request)))
    assert response["error"]["code"] == CONSTRAINT_VIOLATION
    assert response["error"]["data"]["rule_id"] == "grant_amount_limit"
    assert store.count() == 0
