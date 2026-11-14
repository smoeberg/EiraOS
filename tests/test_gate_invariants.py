"""Gate invariants that had no test that a realistic bug would fail
(UDVIKLINGSPLAN F0c.2, review G-21).

Each test here was written because a mutant in tests/mutants/GATE-*.patch
survived the existing suite. The test names the mutant it kills.
"""

from __future__ import annotations

import sqlite3

import tests.test_gate_kernel as kernel_tests
from app.gate import Decision, GateCode
from app.gate.caller import acting_as
from app.gate.policy import Origin
from tests.callers import HUMAN_SESSION, MODEL
from tests.test_gate_kernel import ANNE, _RecordingExecutor, envelope, outbox, propose_and_consent, raw, rh

world = kernel_tests.world  # the same fixture


def _consents(world, action_id):
    with sqlite3.connect(world.db) as conn:
        return conn.execute("SELECT session_id FROM gate_consents WHERE action_id = ?", (action_id,)).fetchall()


def test_a_consent_from_another_session_of_the_same_user_does_not_count(world):
    """GATE-L5-1: a consent is bound to the session it was given in."""
    world.sessions["s-anne-2"] = {**HUMAN_SESSION, "actor_id": "anne@kommune.dk", "assurance_level": "eid_low"}
    env, digest = propose_and_consent(world, session="s-anne")
    result = world.gate.confirm(env["id"], digest, rh(world, env["id"]), "s-anne-2")
    assert (result.decision, result.code, result.layer) == (Decision.REJECT, GateCode.E_CONSENT, 5)
    assert outbox(world) == []


def test_a_revoked_consent_does_not_count(world):
    """GATE-L5-2: revoked_at ends a consent (logout, F1c.2)."""
    env, digest = propose_and_consent(world)
    with sqlite3.connect(world.db) as conn:
        conn.execute("UPDATE gate_consents SET revoked_at = '2026-11-07T09:01:00Z' WHERE action_id = ?", (env["id"],))
    result = world.gate.confirm(env["id"], digest, rh(world, env["id"]), "s-anne")
    assert (result.code, result.layer) == (GateCode.E_CONSENT, 5)
    assert outbox(world) == []


def test_another_user_cannot_consent_to_someone_elses_action(world):
    """GATE-C-1: only the proposing user can consent."""
    proposal = world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL)
    assert proposal.code is GateCode.E_NEED_CONSENT
    result = world.gate.grant_consent("dlg-0001", proposal.content_hash, rh(world, "dlg-0001"), "s-bo")
    assert (result.decision, result.code) == (Decision.REJECT, GateCode.E_UNAUTHORIZED)
    assert _consents(world, "dlg-0001") == []


def test_the_model_is_refused_at_consent_and_confirm(world):
    """GATE-C-4, GATE-C-5: consent and confirmation come from a human, never
    the model, and the refusal says so (E_MODEL_CANNOT_DECIDE), even with a
    proof computed for the model's own uid."""
    proposal = world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL)
    with acting_as(MODEL):
        consent = world.gate.grant_consent("dlg-0001", proposal.content_hash, rh(world, "dlg-0001"), "s-anne")
        confirm = world.gate.confirm("dlg-0001", proposal.content_hash, rh(world, "dlg-0001"), "s-anne")
    assert (consent.decision, consent.code) == (Decision.REJECT, GateCode.E_MODEL_CANNOT_DECIDE)
    assert (confirm.decision, confirm.code) == (Decision.REJECT, GateCode.E_MODEL_CANNOT_DECIDE)
    assert _consents(world, "dlg-0001") == []
    assert outbox(world) == []


def test_a_rendering_text_changed_after_proposal_cannot_be_consented_to(world):
    """GATE-R-1: the stored text must still hash to the stored rendering hash."""
    proposal = world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL)
    digest_shown = rh(world, "dlg-0001")
    with sqlite3.connect(world.db) as conn:
        conn.execute("UPDATE gate_actions SET rendering_text = 'Ingenting sker.' WHERE action_id = 'dlg-0001'")
    result = world.gate.grant_consent("dlg-0001", proposal.content_hash, digest_shown, "s-anne")
    assert (result.decision, result.code) == (Decision.REJECT, GateCode.E_CONSENT)
    assert _consents(world, "dlg-0001") == []


def test_a_confirmation_must_name_the_rendering_that_was_shown(world):
    """GATE-R-2: an action that needs only confirmation (no consent) is still
    bound to the text the user saw."""
    env = envelope("presence_changed", {"state": "busy"}, id="dlg-presence")
    world.gate._registry.register(_RecordingExecutor("presence_changed"))
    proposal = world.gate.propose(raw(env), "s-anne", Origin.USER)
    result = world.gate.confirm("dlg-presence", proposal.content_hash, "sha256:" + "0" * 64, "s-anne")
    assert (result.decision, result.code, result.layer) == (Decision.REJECT, GateCode.E_STATE, 7)
    assert world.gate.gate_state("dlg-presence") == "pending"


def test_the_proposer_is_the_consenting_identity(world):
    """Sanity for the two tests above: the happy path still passes."""
    env, digest = propose_and_consent(world)
    assert world.store.find(env["id"])["actor_identity"] == ANNE
    assert world.gate.confirm(env["id"], digest, rh(world, env["id"]), "s-anne").decision is Decision.PASS


def test_a_session_that_has_ended_cannot_confirm(world):
    """GATE-S-1: logout (F1c.2) ends a session by setting expires_at to now;
    the gate must refuse the session from then on, also for an action that
    was already consented to."""
    env, digest = propose_and_consent(world)
    world.sessions["s-anne"] = {**world.sessions["s-anne"], "expires_at": "2026-11-07T08:59:00Z"}
    result = world.gate.confirm(env["id"], digest, rh(world, env["id"]), "s-anne")
    assert result.decision is Decision.REJECT
    assert outbox(world) == []
