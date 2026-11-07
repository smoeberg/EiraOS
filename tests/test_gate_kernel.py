"""Gate Kernel 1.0 acceptance tests (specs/GATE-KERNEL-1.0.md §7).

Rule from the spec: no test may pass because the model "behaves". Every
rejection test feeds input that looks correct apart from the one thing the
gate must catch.
"""

from __future__ import annotations

import copy
import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

from app.gate import Decision, Gate, GateCode
from app.gate import policy as gate_policy
from app.gate.executors import (
    ConversationOutboxExecutor,
    DirectCallRejected,
    Executor,
    ExecutorRegistry,
    ExecutorResult,
    GateTicket,
    default_registry,
)
from app.gate.policy import Origin
from app.gate.store import GateStore

CONV = "obj:sag:42"
ANNE = "did:eira:anne"
BO = "did:eira:bo"


def envelope(action_type="commitment_proposed", content=None, **overrides):
    env = {
        "edp": "1.0",
        "id": "dlg-0001",
        "conversation_id": CONV,
        "participants": [
            {"identity": ANNE, "role": "member"},
            {"identity": "external:sms:+4512345678", "role": "member"},
        ],
        "action": {
            "type": action_type,
            "content": content
            if content is not None
            else {"what": "Møde om budgettet", "when": "2026-11-12T10:00:00+01:00"},
        },
        "transport": {"preferred": ["eira-native", "sms"], "actual": None, "degraded": False, "error": None},
        "veritas": {"status": "unassessed", "trust_score": None, "evidence_refs": []},
        "temporal": {"created_at": "2026-11-07T09:00:00Z", "valid_from": None, "supersedes": None},
    }
    env.update(overrides)
    return env


def raw(env) -> str:
    return json.dumps(env, ensure_ascii=False)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


@pytest.fixture
def world(tmp_path):
    db = str(tmp_path / "gate.db")
    store = GateStore(db)
    sessions = {
        "s-anne": {"actor_id": "anne@kommune.dk", "assurance_level": "eid_low"},
        "s-bo": {"actor_id": "bo@kommune.dk", "assurance_level": "eid_high"},
    }
    store.bind_identity("anne@kommune.dk", ANNE)
    store.bind_identity("bo@kommune.dk", BO)
    store.add_member(CONV, ANNE)
    grant = store.grant_right(ANNE, CONV, "*")
    clock = Clock()
    gate = Gate(store, default_registry(db), sessions=sessions.get, clock=clock)

    class World:
        pass

    w = World()
    w.db, w.store, w.sessions, w.grant, w.clock, w.gate = db, store, sessions, grant, clock, gate
    return w


def propose_and_consent(world, env=None, session="s-anne", origin=Origin.MODEL):
    env = env or envelope()
    proposal = world.gate.propose(raw(env), session, origin)
    assert proposal.code is GateCode.E_NEED_CONSENT, proposal
    consent = world.gate.grant_consent(env["id"], proposal.content_hash, session)
    assert consent.code is None, consent
    return env, proposal.content_hash


def outbox(world):
    with sqlite3.connect(world.db) as conn:
        return conn.execute("SELECT event_id, delivery_state FROM conversation_outbox").fetchall()


# --- the happy path: "samtale om en sag" ----------------------------------------


def test_a_proposed_meeting_is_recorded_as_proposed_not_as_delivered(world):
    env, digest = propose_and_consent(world)
    result = world.gate.confirm(env["id"], digest, "s-anne")
    assert result.decision is Decision.PASS
    assert result.state == "executed"
    assert result.result["visible_state"] == "proposed"
    assert result.result["delivery"] == "pending"
    assert outbox(world) == [("dlg-0001", "pending")]
    assert world.gate.status("dlg-0001")["state"] == "executed"


def test_propose_alone_never_executes(world):
    result = world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL)
    assert result.decision is Decision.REJECT
    assert result.code is GateCode.E_NEED_CONSENT
    assert result.state == "pending"
    assert outbox(world) == []


def test_idempotent_actions_need_no_consent_but_still_confirmation(world):
    env = envelope("presence_changed", {"state": "busy"}, id="dlg-presence")
    world.gate._registry.register(_RecordingExecutor("presence_changed"))
    proposal = world.gate.propose(raw(env), "s-anne", Origin.USER)
    assert proposal.decision is None and proposal.state == "pending"
    assert world.gate.confirm("dlg-presence", proposal.content_hash, "s-anne").decision is Decision.PASS


# --- §7 acceptance table ------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, "", "{", "[1,2]", '{"edp":"1.0","edp":"1.0"}', "NaN", b"\xff\xfe"])
def test_invalid_json_is_rejected_as_syntax(world, bad):
    result = world.gate.propose(bad, "s-anne", Origin.MODEL)
    assert (result.decision, result.code, result.layer) == (Decision.REJECT, GateCode.E_SYNTAX, 1)


def test_wrong_edp_version_and_missing_created_at_are_syntax_errors(world):
    assert world.gate.propose(raw(envelope(edp="2.0")), "s-anne", Origin.MODEL).code is GateCode.E_SYNTAX
    env = envelope()
    del env["temporal"]["created_at"]
    assert world.gate.propose(raw(env), "s-anne", Origin.MODEL).code is GateCode.E_SYNTAX


def test_unknown_action_type_is_rejected_as_schema(world):
    result = world.gate.propose(raw(envelope("delete_everything", {"what": "x"})), "s-anne", Origin.MODEL)
    assert (result.decision, result.code, result.layer) == (Decision.REJECT, GateCode.E_SCHEMA, 2)


def test_missing_content_field_is_rejected_as_schema(world):
    result = world.gate.propose(raw(envelope(content={"when": "tomorrow"})), "s-anne", Origin.MODEL)
    assert result.code is GateCode.E_SCHEMA


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e.update(confidence=0.99),  # confidence is never authorization
        lambda e: e["action"].update(reversibility="idempotent"),  # class is gate-internal
        lambda e: e.update(conversation_id="sms:+4512345678"),  # channel, not object
        lambda e: e["participants"].append({"identity": "root", "role": "member"}),
        lambda e: e["temporal"].update(created_at="7. november"),
        lambda e: e["veritas"].update(trust_score=1.5),
        lambda e: e["transport"].update(degraded="yes"),
    ],
)
def test_schema_rejects_lookalike_input(world, mutate):
    env = envelope()
    mutate(env)
    assert world.gate.propose(raw(env), "s-anne", Origin.MODEL).code is GateCode.E_SCHEMA


def test_semantic_errors_and_clarify(world):
    accept = envelope("commitment_accepted", {"commitment_id": "dlg-nope"}, id="dlg-acc")
    assert world.gate.propose(raw(accept), "s-anne", Origin.MODEL).code is GateCode.E_SEMANTIC

    early = envelope()
    early["temporal"]["valid_from"] = "2026-11-06T09:00:00Z"
    assert world.gate.propose(raw(early), "s-anne", Origin.MODEL).code is GateCode.E_SEMANTIC

    blank = envelope(content={"what": "   "})
    result = world.gate.propose(raw(blank), "s-anne", Origin.MODEL)
    assert (result.decision, result.code, result.layer) == (Decision.CLARIFY, GateCode.E_MISSING_FIELD, 3)


def test_forbidden_action_and_parameters_are_rejected_as_policy(world):
    # Only a payment provider may confirm a transfer; never a model or a user.
    confirmed = envelope("value_transfer_confirmed", {"transfer_ref": "t-1"}, id="dlg-vt")
    assert world.gate.propose(raw(confirmed), "s-anne", Origin.MODEL).code is GateCode.E_POLICY
    # Consent can only be granted by the user, never proposed by a model.
    granted = envelope("consent_granted", {"consent_ref": "c-1"}, id="dlg-cg")
    assert world.gate.propose(raw(granted), "s-anne", Origin.MODEL).code is GateCode.E_POLICY
    # Amount above the policy limit.
    big = envelope(
        "value_transfer_requested", {"amount": {"value": "250000.00", "currency": "DKK"}}, id="dlg-big"
    )
    assert world.gate.propose(raw(big), "s-anne", Origin.USER).code is GateCode.E_POLICY
    # A conversation outside the user's domain.
    other = envelope(conversation_id="obj:sag:99", id="dlg-other")
    assert world.gate.propose(raw(other), "s-anne", Origin.MODEL).code is GateCode.E_POLICY


def test_degraded_transport_does_not_skip_validation(world):
    env = envelope("delete_everything", {"what": "x"})
    env["transport"].update(degraded=True, error={"code": "E_DEGRADED_CONTENT"})
    assert world.gate.propose(raw(env), "s-anne", Origin.MODEL).code is GateCode.E_SCHEMA


def test_missing_consent_for_irreversible_action_is_rejected(world):
    proposal = world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL)
    result = world.gate.confirm("dlg-0001", proposal.content_hash, "s-anne")
    assert (result.decision, result.code, result.layer) == (Decision.REJECT, GateCode.E_CONSENT, 5)
    assert outbox(world) == []


def test_consent_expires(world):
    env, digest = propose_and_consent(world)
    world.clock.now += timedelta(minutes=11)
    assert world.gate.confirm(env["id"], digest, "s-anne").code is GateCode.E_CONSENT


def test_changed_parameters_after_confirmation_are_rejected(world):
    env, digest = propose_and_consent(world)
    # Same id, different meeting time: a new proposal cannot reuse the id.
    changed = copy.deepcopy(env)
    changed["action"]["content"]["when"] = "2026-11-13T10:00:00+01:00"
    reuse = world.gate.propose(raw(changed), "s-anne", Origin.MODEL)
    assert (reuse.code, reuse.layer) == (GateCode.E_STATE, 7)
    # A confirmation bound to other parameters is rejected too.
    other = world.gate.propose(raw(changed | {"id": "dlg-0002"}), "s-anne", Origin.MODEL)
    assert world.gate.confirm(env["id"], other.content_hash, "s-anne").code is GateCode.E_STATE
    # Consent for the original does not cover the changed one.
    world.gate.grant_consent("dlg-0002", other.content_hash, "s-anne")
    assert world.gate.confirm("dlg-0002", digest, "s-anne").code is GateCode.E_STATE
    assert outbox(world) == []


def test_tampered_stored_input_is_rejected(world):
    env, digest = propose_and_consent(world)
    tampered = copy.deepcopy(env)
    tampered["action"]["content"]["what"] = "Overfør 10.000 kr"
    with sqlite3.connect(world.db) as conn:
        conn.execute("UPDATE gate_actions SET raw = ? WHERE action_id = ?", (raw(tampered), env["id"]))
    assert world.gate.confirm(env["id"], digest, "s-anne").code is GateCode.E_STATE


def test_double_execution_returns_the_existing_result(world):
    env, digest = propose_and_consent(world)
    first = world.gate.confirm(env["id"], digest, "s-anne")
    second = world.gate.confirm(env["id"], digest, "s-anne")
    assert first.decision is second.decision is Decision.PASS
    assert first.execution_id == second.execution_id
    assert len(outbox(world)) == 1


def test_concurrent_confirmations_execute_once(world):
    env, digest = propose_and_consent(world)
    results = []
    barrier = threading.Barrier(8)

    def go():
        barrier.wait()
        results.append(world.gate.confirm(env["id"], digest, "s-anne"))

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(outbox(world)) == 1
    passed = [r for r in results if r.decision is Decision.PASS]
    assert passed and len({r.execution_id for r in passed}) == 1
    assert all(r.decision is Decision.PASS or r.code is GateCode.E_STATE for r in results)


def test_right_revoked_after_planning_is_rejected(world):
    env, digest = propose_and_consent(world)
    world.store.revoke_right(world.grant)
    result = world.gate.confirm(env["id"], digest, "s-anne")
    assert (result.code, result.layer) == (GateCode.E_UNAUTHORIZED, 6)
    assert outbox(world) == []
    assert world.gate.status(env["id"])["state"] == "pending"


def test_right_revoked_between_claim_and_execution_is_rejected(world, monkeypatch):
    env, digest = propose_and_consent(world)
    original_claim = world.store.claim

    def claim_then_revoke(*args):
        execution_id = original_claim(*args)
        world.store.revoke_right(world.grant)
        return execution_id

    monkeypatch.setattr(world.store, "claim", claim_then_revoke)
    result = world.gate.confirm(env["id"], digest, "s-anne")
    assert result.code is GateCode.E_UNAUTHORIZED
    assert outbox(world) == []
    assert world.gate.status(env["id"])["state"] == "pending"


def test_executor_cannot_be_called_directly(world):
    executor = world.gate._registry.executor("commitment_proposed")
    registry = world.gate._registry
    env = envelope()
    with pytest.raises(DirectCallRejected):
        registry.call(None, env, "sha256:x")
    forged = GateTicket(env["id"], "sha256:x", "exec-1", "0" * 64)
    with pytest.raises(DirectCallRejected):
        registry.call(forged, env, "sha256:x")
    # A real ticket works once only, and only for its own action.
    ticket = registry.issue(env["id"], "sha256:x", "exec-1")
    with pytest.raises(DirectCallRejected):
        registry.call(ticket, env | {"id": "dlg-other"}, "sha256:x")
    registry.call(ticket, env, "sha256:x")
    with pytest.raises(DirectCallRejected):
        registry.call(ticket, env, "sha256:x")
    assert isinstance(executor, ConversationOutboxExecutor)


def test_unavailable_model_runtime_is_a_safe_reject(world):
    def crashing_model():
        raise ConnectionError("ollama is down")

    for produce in (crashing_model, lambda: None, lambda: "Beklager, jeg kan ikke svare som JSON"):
        result = world.gate.propose_from_model(produce, "s-anne")
        assert (result.decision, result.code) == (Decision.REJECT, GateCode.E_SYNTAX)
    assert outbox(world) == []


def test_partial_failure_is_reported_with_its_state(world):
    world.gate._registry = _registry_with(world, _PartialExecutor())
    env, digest = propose_and_consent(world)
    result = world.gate.confirm(env["id"], digest, "s-anne")
    assert (result.decision, result.code, result.state) == (Decision.REJECT, GateCode.E_PARTIAL, "partial")
    assert world.gate.status(env["id"])["state"] == "partial"
    # Not retried automatically.
    again = world.gate.confirm(env["id"], digest, "s-anne")
    assert again.code is GateCode.E_PARTIAL and again.execution_id == result.execution_id


def test_executor_crash_is_unknown_never_success(world):
    world.gate._registry = _registry_with(world, _CrashingExecutor())
    env, digest = propose_and_consent(world)
    result = world.gate.confirm(env["id"], digest, "s-anne")
    assert (result.code, result.state) == (GateCode.E_PARTIAL, "unknown")


def test_invalid_state_transition_from_executor_is_not_success(world):
    world.gate._registry = _registry_with(world, _LyingExecutor())
    env, digest = propose_and_consent(world)
    result = world.gate.confirm(env["id"], digest, "s-anne")
    assert (result.code, result.state) == (GateCode.E_PARTIAL, "unknown")


def test_missing_executor_is_reported_and_nothing_changes(world):
    env = envelope("artifact_shared", {"artifact_ref": "obj:document:7"}, id="dlg-art")
    env, digest = propose_and_consent(world, env)
    result = world.gate.confirm(env["id"], digest, "s-anne")
    assert (result.code, result.layer) == (GateCode.E_EXECUTOR_UNAVAILABLE, 8)
    assert world.gate.status(env["id"])["state"] == "pending"


def test_correct_schema_without_permission_is_unauthorized(world):
    # Bo is a member of the conversation but has no right to propose there.
    world.store.add_member(CONV, BO)
    env = envelope(participants=[{"identity": BO, "role": "member"}], id="dlg-bo")
    result = world.gate.propose(raw(env), "s-bo", Origin.MODEL)
    assert result.code is GateCode.E_NEED_CONSENT  # consent is checked before rights
    world.gate.grant_consent("dlg-bo", result.content_hash, "s-bo")
    result = world.gate.confirm("dlg-bo", result.content_hash, "s-bo")
    assert (result.decision, result.code, result.layer) == (Decision.REJECT, GateCode.E_UNAUTHORIZED, 6)


def test_acting_for_someone_else_is_unauthorized(world):
    # Anne's session proposes a message that only lists Bo as sender.
    world.store.add_member(CONV, BO)
    env = envelope(participants=[{"identity": BO, "role": "member"}], id="dlg-spoof")
    proposal = world.gate.propose(raw(env), "s-anne", Origin.MODEL)
    world.gate.grant_consent("dlg-spoof", proposal.content_hash, "s-anne")
    assert world.gate.confirm("dlg-spoof", proposal.content_hash, "s-anne").code is GateCode.E_UNAUTHORIZED


def test_unknown_or_missing_session_cannot_act(world):
    for session in (None, "", "s-forged"):
        result = world.gate.propose(raw(envelope(id=f"dlg-{session}")), session, Origin.MODEL)
        assert result.decision is Decision.REJECT
    env, digest = propose_and_consent(world)
    assert world.gate.confirm(env["id"], digest, "s-forged").decision is Decision.REJECT
    assert world.gate.grant_consent(env["id"], digest, "s-forged").code is GateCode.E_UNAUTHORIZED


def test_step_up_required_for_payments(world):
    env = envelope(
        "value_transfer_requested", {"amount": {"value": "100.00", "currency": "DKK"}}, id="dlg-pay"
    )
    env, digest = propose_and_consent(world, env, origin=Origin.USER)
    result = world.gate.confirm(env["id"], digest, "s-anne")
    assert (result.code, result.layer) == (GateCode.E_STEP_UP_REQUIRED, 6)
    assert result.data["required_assurance"] == "eid_high"


def test_policy_change_after_proposal_forces_reject(world, monkeypatch):
    env, digest = propose_and_consent(world)
    stricter = gate_policy.ActionPolicy(
        "commitment_proposed",
        gate_policy.Reversibility.IRREVERSIBLE,
        frozenset({Origin.MODEL, Origin.USER}),
        required_assurance="eid_high",
    )
    monkeypatch.setitem(gate_policy.REGISTRY, "commitment_proposed", stricter)
    assert world.gate.confirm(env["id"], digest, "s-anne").code is GateCode.E_POLICY


def test_unknown_policy_entry_is_treated_as_not_allowed(world, monkeypatch):
    monkeypatch.delitem(gate_policy.REGISTRY, "utterance")
    env = envelope("utterance", {"text": "Hej"}, id="dlg-u")
    assert world.gate.propose(raw(env), "s-anne", Origin.MODEL).code is GateCode.E_POLICY


def test_accepting_requires_a_proposed_commitment_in_the_same_conversation(world):
    env, digest = propose_and_consent(world)
    world.gate.confirm(env["id"], digest, "s-anne")
    accept = envelope("commitment_accepted", {"commitment_id": env["id"]}, id="dlg-acc")
    proposal = world.gate.propose(raw(accept), "s-anne", Origin.USER)
    assert proposal.code is GateCode.E_NEED_CONSENT
    world.store.add_member("obj:sag:43", ANNE)
    cross = envelope(
        "commitment_accepted", {"commitment_id": env["id"]}, id="dlg-x", conversation_id="obj:sag:43"
    )
    assert world.gate.propose(raw(cross), "s-anne", Origin.USER).code is GateCode.E_SEMANTIC


# --- audit ------------------------------------------------------------------


def test_every_decision_is_audited_and_pass_only_after_the_result(world):
    world.gate.propose("{", "s-anne", Origin.MODEL)
    env, digest = propose_and_consent(world)
    world.gate.confirm(env["id"], digest, "s-anne")
    entries = [json.loads(row["entry"]) for row in world.store.audit_entries()]
    assert [(e["step"], e["decision"], e["error"]) for e in entries] == [
        ("propose", "REJECT", "E_SYNTAX"),
        ("propose", "REJECT", "E_NEED_CONSENT"),
        ("consent", None, None),
        ("confirm", "PASS", None),
    ]
    assert entries[-1]["layer"] == 8 and entries[-1]["participant"] == ANNE
    assert all(e["gate"] == "1.0" and e["policy_version"] == gate_policy.POLICY_VERSION for e in entries)
    assert world.store.verify_audit_chain()


def test_audit_log_is_append_only_and_tamper_evident(world):
    world.gate.propose("{", "s-anne", Origin.MODEL)
    world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL)
    with sqlite3.connect(world.db) as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE gate_audit SET entry = '{}' WHERE seq = 1")
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM gate_audit")
        # Even bypassing the triggers is detected by the hash chain.
        conn.execute("DROP TRIGGER gate_audit_no_update")
        conn.execute('UPDATE gate_audit SET entry = \'{"decision":"PASS"}\' WHERE seq = 1')
    assert not world.store.verify_audit_chain()


def test_bundled_schema_matches_the_spec():
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    assert (repo / "app/gate/edp-1.0.schema.json").read_text() == (
        repo / "specs/edp-1.0.schema.json"
    ).read_text()


# --- helpers -----------------------------------------------------------------


class _RecordingExecutor(Executor):
    success_transitions = frozenset({("executing", "recorded")})

    def __init__(self, action_type):
        self.action_type = action_type

    def run(self, envelope, execution_id):
        return ExecutorResult("succeeded", ("executing", "recorded"), {"visible_state": "set"})


class _PartialExecutor(_RecordingExecutor):
    def __init__(self):
        super().__init__("commitment_proposed")

    def run(self, envelope, execution_id):
        return ExecutorResult("partial", ("executing", "partial"), {"sent_to": 1, "of": 2})


class _CrashingExecutor(_RecordingExecutor):
    def __init__(self):
        super().__init__("commitment_proposed")

    def run(self, envelope, execution_id):
        raise TimeoutError("adapter timed out")


class _LyingExecutor(_RecordingExecutor):
    def __init__(self):
        super().__init__("commitment_proposed")

    def run(self, envelope, execution_id):
        return ExecutorResult("succeeded", ("pending", "delivered"), {})


def _registry_with(world, executor):
    registry = ExecutorRegistry()
    registry.register(executor)
    return registry
