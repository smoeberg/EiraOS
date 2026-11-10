"""Lag 4 for a model proposal (EIRA-DELEGATION-1.0 §4): only under a live
delegation from the human whose session it acts in, recorded in the gate's own
audit chain, with no other system on the decision path."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.auth.delegation import DelegationRevokeRequest
from app.gate import GateCode
from app.gate import caller as caller_module
from app.gate.caller import acting_as
from app.gate.policy import Origin
from tests.callers import MODEL
from tests.test_gate_kernel import ANNE, BO, CONV, envelope, raw
from tests.test_gate_kernel import world as world  # noqa: F401  (fixture)

pytestmark = pytest.mark.usefixtures("model_uid_990")


@pytest.fixture
def model_uid_990(monkeypatch):
    monkeypatch.setattr(caller_module, "model_uid", lambda: MODEL.uid)


def as_model(world, session="s-anne", env=None):
    with acting_as(MODEL):
        return world.gate.propose(raw(env or envelope()), session, Origin.MODEL)


def test_the_model_proposes_under_anne_s_delegation_and_the_gate_records_which(world):
    result = as_model(world)
    assert result.code is GateCode.E_NEED_CONSENT, result
    entries = [json.dumps(dict(e), default=str) for e in world.store.audit_entries()]
    [delegation] = world.delegation.repo.active_for_delegator(ANNE)
    assert any(delegation.id in entry for entry in entries)


def test_without_a_delegation_from_this_human_the_model_cannot_propose(world):
    world.store.add_member(CONV, BO)
    result = as_model(world, "s-bo", envelope(id="dlg-bo"))
    assert result.code is GateCode.E_UNAUTHORIZED and "delegation" in result.detail
    assert world.store.find("dlg-bo") is None  # stopped before anything was stored


def test_a_revoked_delegation_stops_the_model(world):
    [delegation] = world.delegation.repo.active_for_delegee(caller_module.model_identity(MODEL))
    with patch.object(world.delegation, "_audit"):
        world.delegation.revoke_delegation(DelegationRevokeRequest(delegation_id=delegation.id),
                                           delegation.delegator_id)
    result = as_model(world)
    assert result.code is GateCode.E_UNAUTHORIZED and "delegation" in result.detail


def test_no_second_audit_system_on_the_decision_path(world, monkeypatch):
    """The old design called stated over IPC in lag 4; an unreachable stated
    then rejected every model proposal."""
    from app.ipc import client

    def unreachable(*_args, **_kwargs):
        raise ConnectionError("stated is down")

    monkeypatch.setattr(client.IpcClient, "call", unreachable)
    assert as_model(world).code is GateCode.E_NEED_CONSENT


def test_a_human_proposal_needs_no_delegation(world):
    world.store.add_member(CONV, BO)
    result = world.gate.propose(raw(envelope(id="dlg-human")), "s-bo", Origin.USER)
    assert result.code is not GateCode.E_UNAUTHORIZED or result.layer != 4
