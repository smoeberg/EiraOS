"""Trusted path for consent (GATE-KERNEL bilag A pkt. 1): consent and
confirmation carry a proof only the EiraOS app can make."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.gate import GateCode, consent_proof
from app.gate.policy import Origin
from tests.callers import CONSENT_KEY, HUMAN
from tests.test_gate_kernel import envelope, raw, rh
from tests.test_gate_kernel import world as world  # noqa: F401  (fixture)

VECTORS = json.loads((Path(__file__).parent / "vectors" / "consent-proof.json").read_text())


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["verb"])
def test_shared_vectors(case):
    args = {k: case[k] for k in ("uid", "session_id", "action_id", "content_hash", "rendering_hash")}
    assert consent_proof.compute(case["key"], case["verb"], **args) == case["proof"]


def _proposed(world):
    proposal = world.gate.propose(raw(envelope()), "s-anne", Origin.USER)
    return proposal.content_hash, rh(world, "dlg-0001")


def _bare(world):
    return world.gate._gate  # the kernel itself, without the test app's proof


def _proof(verb, digest, rendering, *, key=CONSENT_KEY, uid=HUMAN.uid, action="dlg-0001", session="s-anne"):
    return consent_proof.compute(key, verb, uid, session, action, digest, rendering)


def test_another_program_as_the_same_user_cannot_consent(world):
    """Same uid, valid session id, no key: refused, with its own code."""
    digest, rendering = _proposed(world)
    result = _bare(world).grant_consent("dlg-0001", digest, rendering, "s-anne")
    assert result.code is GateCode.E_CONSENT_PROOF
    assert world.gate.status("dlg-0001", "s-anne")["state"] == "pending"


@pytest.mark.parametrize(
    "bad",
    [
        {"key": "22" * 32},                    # another key
        {"uid": 1001},                         # proof made for another user
        {"action": "dlg-9999"},                # for another action
        {"session": "s-other"},                # for another session
    ],
    ids=["key", "uid", "action", "session"],
)
def test_proof_is_bound_to_key_user_action_and_session(world, bad):
    digest, rendering = _proposed(world)
    proof = _proof("consent", digest, rendering, **bad)
    assert _bare(world).grant_consent("dlg-0001", digest, rendering, "s-anne", proof).code is GateCode.E_CONSENT_PROOF


def test_proof_is_bound_to_the_verb_and_the_rendering(world):
    digest, rendering = _proposed(world)
    gate = _bare(world)
    assert gate.grant_consent("dlg-0001", digest, rendering, "s-anne",
                              _proof("confirm", digest, rendering)).code is GateCode.E_CONSENT_PROOF
    assert gate.grant_consent("dlg-0001", digest, rendering, "s-anne",
                              _proof("consent", digest, "sha256:" + "0" * 64)).code is not None
    ok = gate.grant_consent("dlg-0001", digest, rendering, "s-anne", _proof("consent", digest, rendering))
    assert ok.code is None and ok.state == "pending"
    assert gate.confirm("dlg-0001", digest, rendering, "s-anne",
                        _proof("consent", digest, rendering)).code is GateCode.E_CONSENT_PROOF
    assert gate.confirm("dlg-0001", digest, rendering, "s-anne",
                        _proof("confirm", digest, rendering)).decision.value == "PASS"


def test_session_without_a_key_cannot_consent(world):
    digest, rendering = _proposed(world)
    world.sessions["s-anne"].pop("consent_key")
    result = world.gate.grant_consent("dlg-0001", digest, rendering, "s-anne")
    assert result.code is GateCode.E_CONSENT_PROOF


def test_refusal_is_audited_with_its_own_code(world):
    digest, rendering = _proposed(world)
    _bare(world).confirm("dlg-0001", digest, rendering, "s-anne", "0" * 64)
    with world.store._connect() as conn:
        entry = json.loads(conn.execute("SELECT entry FROM gate_audit ORDER BY seq DESC LIMIT 1").fetchone()["entry"])
    assert entry["error"] == "E_CONSENT_PROOF" and entry["caller"]["uid"] == HUMAN.uid


def test_malformed_input_never_verifies():
    assert not consent_proof.verify(None, "0" * 64, "consent", 1, "s", "a", "c", "r")
    assert not consent_proof.verify(CONSENT_KEY, None, "consent", 1, "s", "a", "c", "r")
    assert not consent_proof.verify(CONSENT_KEY, "x", "consent", 1, "s", "a", "c", "r")
    assert not consent_proof.verify(CONSENT_KEY, "0" * 64, "delete", 1, "s", "a", "c", "r")
    assert not consent_proof.verify(CONSENT_KEY, "0" * 64, "consent", 1, "s\0x", "a", "c", "r")
    assert not consent_proof.verify("not-hex", "0" * 64, "consent", 1, "s", "a", "c", "r")
