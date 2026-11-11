"""Layer 6 against the Fleet-signed rights set (EIRA-RIGHTS-SET-1.0 §6,
ADR-0003). The set is the only source of rights."""

from __future__ import annotations

import json
from datetime import timedelta

from app.gate import Decision, Gate, GateCode
from app.gate.executors import default_registry
from app.gate.policy import Origin
from app.gate.store import GateStore
from app.rights import contract
from app.rights.cache import RightsCache
from tests.callers import HUMAN_SESSION, ProvingGate
from tests.rights_helpers import TestFleet
from tests.test_gate_kernel import (
    ANNE,
    CONV,
    BootClock,
    Clock,
    envelope,
    propose_and_consent,
    rh,
)


def last_audit(store: GateStore) -> dict:
    with store._connect() as conn:
        row = conn.execute("SELECT entry FROM gate_audit ORDER BY seq DESC LIMIT 1").fetchone()
    return json.loads(row["entry"])


class W:
    pass


def make_world(tmp_path, *, kind="managed", grant=True):
    w = W()
    w.db = str(tmp_path / "gate.db")
    w.store = GateStore(w.db)
    w.sessions = {
        "s-anne": {**HUMAN_SESSION, "actor_id": "anne@kommune.dk", "assurance_level": "eid_low"},
        "s-anne-group": {**HUMAN_SESSION, "actor_id": "anne@kommune.dk", "assurance_level": "eid_low", "groups": ["laerere"]},
    }
    w.store.bind_identity("anne@kommune.dk", ANNE)
    w.store.add_member(CONV, ANNE)
    w.clock, w.boot = Clock(), BootClock()
    w.fleet = TestFleet(tmp_path / "rights", w.clock, boot_clock=w.boot, kind=kind)
    if grant:
        w.fleet.grant(CONV, principal=ANNE).publish()
    w.gate = ProvingGate(Gate(
        w.store, default_registry(w.db), sessions=w.sessions.get, clock=w.clock,
        boot_clock=w.boot, rights=w.fleet.cache,
    ), w.sessions.get)
    return w


def attempt(w, env=None, session="s-anne"):
    """Layer 6 decides after consent: propose → consent → confirm."""
    env, digest = propose_and_consent(w, env, session)
    return w.gate.confirm(env["id"], digest, rh(w, env["id"]), session)


def test_no_rights_set_means_no_rights(tmp_path):
    w = make_world(tmp_path, grant=False)
    result = attempt(w)
    assert (result.decision, result.code, result.layer) == (Decision.REJECT, GateCode.E_UNAUTHORIZED, 6)
    assert result.data["rights"] == "missing"
    assert w.gate.rights_status() == {"state": "missing", "reason": "no_rights_set"}


def test_pass_is_audited_with_the_set_and_the_grant(tmp_path):
    w = make_world(tmp_path)
    result = attempt(w)
    assert result.decision is Decision.PASS
    entry = last_audit(w.store)
    assert entry["rights_set_id"] == "00000000-0000-7000-8000-000000000001"
    assert (entry["rights_version"], entry["rights_kind"], entry["rights_grant"]) == (1, "managed", 0)
    assert entry["owner_admin"] is False
    assert (entry["rights_template"], entry["rights_api_call_id"]) == ("test", "test-1")  # §6


def test_group_grant_from_the_session(tmp_path):
    w = make_world(tmp_path, grant=False)
    w.fleet.grant(CONV, group="laerere").publish()
    assert attempt(w).code is GateCode.E_UNAUTHORIZED
    assert attempt(w, envelope(id="dlg-0002"), "s-anne-group").decision is Decision.PASS


def test_deny_wins_over_grant(tmp_path):
    w = make_world(tmp_path)
    w.fleet.deny(CONV, ["edp:commitment_proposed"], principal=ANNE).publish()
    result = attempt(w)
    assert (result.code, result.layer) == (GateCode.E_UNAUTHORIZED, 6)
    assert "denied" in result.detail


def test_grant_can_raise_assurance_and_asks_for_step_up(tmp_path):
    w = make_world(tmp_path, grant=False)
    w.fleet.grant(CONV, principal=ANNE, required_assurance="eid_high").publish()
    result = attempt(w)
    assert result.code is GateCode.E_STEP_UP_REQUIRED
    assert result.data["required_assurance"] == "eid_high"


def test_set_expiry_is_checked_at_confirm_not_only_at_apply(tmp_path):
    """§6: TTL at every decision. A consent given before expiry does not
    carry the action past it."""
    w = make_world(tmp_path)
    w.fleet.ttl = timedelta(minutes=8)
    w.fleet.publish()
    env, digest = propose_and_consent(w)
    w.clock.now += timedelta(minutes=9)
    result = w.gate.confirm(env["id"], digest, rh(w, env["id"]), "s-anne")
    assert (result.code, result.layer) == (GateCode.E_UNAUTHORIZED, 6)
    assert result.data["rights"] == "expired"
    assert w.gate.status(env["id"], "s-anne")["state"] == "pending"


def test_setting_the_clock_back_does_not_revive_an_expired_set(tmp_path):
    """§4.1: elapsed CLOCK_BOOTTIME since apply counts even if the wall clock
    is set back to before expiry."""
    w = make_world(tmp_path)
    w.fleet.ttl = timedelta(hours=1)
    w.fleet.publish()
    w.boot.advance(timedelta(hours=2))
    result = attempt(w)
    assert result.data.get("rights") == "expired"
    assert w.gate.rights_status()["state"] == "expired"


def test_high_water_mark_survives_clock_rollback_and_is_audited(tmp_path):
    w = make_world(tmp_path)
    w.clock.now += timedelta(days=3)
    assert w.gate.rights_status()["clock_rollback"] is False
    w.clock.now -= timedelta(days=2)
    status = w.gate.rights_status()
    assert status["clock_rollback"] is True
    attempt(w)
    assert last_audit(w.store)["clock_rollback"] is True


def test_private_machine_is_marked_owner_admin(tmp_path):
    """ADR-0003 (b): the default set means the owner has root; every decision
    says so, and the gate's verdict is unchanged by it."""
    w = make_world(tmp_path, kind="default", grant=False)
    w.fleet.grant(CONV).publish()
    assert attempt(w).decision is Decision.PASS
    assert last_audit(w.store)["owner_admin"] is True
    assert w.gate.rights_status()["owner_admin"] is True


def test_failure_before_layer_6_does_not_inherit_the_previous_rights(tmp_path):
    w = make_world(tmp_path)
    attempt(w)
    assert last_audit(w.store)["rights_set_id"] is not None
    w.gate.propose("{not json", "s-anne", Origin.MODEL)  # fails in layer 1
    assert last_audit(w.store)["rights_set_id"] is None


# --- cache --------------------------------------------------------------------


def test_cache_refuses_a_rejected_verdict(tmp_path):
    cache = RightsCache(tmp_path / "r")
    try:
        cache.install(b"{}", contract.Verdict(ok=False, reason="schema"), Clock()())
    except ValueError:
        pass
    else:
        raise AssertionError("installed a rejected set")
    assert cache.current(Clock()()) is None


def test_tampered_cache_file_fails_closed(tmp_path):
    w = make_world(tmp_path)
    path = w.fleet.cache.directory / "active.json"
    path.write_text(path.read_text().replace('"version":1', '"version":2'))
    assert w.gate.rights_status() == {"state": "missing", "reason": "no_rights_set"}


def test_unparseable_state_fails_closed(tmp_path):
    w = make_world(tmp_path)
    (w.fleet.cache.directory / "state.json").write_text("{")
    assert attempt(w).code is GateCode.E_UNAUTHORIZED


def test_older_version_cannot_replace_the_active_set(tmp_path):
    from app.gate.policy import REGISTRY

    w = make_world(tmp_path)
    w.fleet.publish()  # version 2 is active
    w.fleet.version = 1  # a correctly signed, older set is replayed
    replay = contract.canonical(w.fleet.document())
    verdict = contract.verify(
        replay, anchors=w.fleet.anchors, device=contract.Device(True, "test-tenant", "test-device"),
        active=w.fleet.cache.active_meta(), now=w.clock(), registry=REGISTRY,
    )
    assert verdict.reason == "version_rollback"


def test_capabilities_show_rights_status_read_only(tmp_path):
    from app.gate.ipc import register_gate_handlers

    w = make_world(tmp_path)

    class Server:
        methods = {}

        def register(self, name, handler):
            self.methods[name] = handler

    server = Server()
    register_gate_handlers(server, w.gate)
    rights = server.methods["gate.capabilities"]({})["rights"]
    assert rights["state"] == "active" and rights["rights_version"] == 1
    assert not any("right" in name for name in server.methods if name != "gate.capabilities")


# --- enrollment is weighed at every decision (review of #146) ------------------


def test_default_set_does_not_survive_enrollment(tmp_path):
    """A private machine that is enrolled loses its default set and
    owner_admin at once, before the first managed set arrives."""
    from tests.rights_helpers import TestFleet as Signer

    w = make_world(tmp_path, kind="default", grant=False)
    w.fleet.grant(CONV).publish()
    assert attempt(w).decision is Decision.PASS
    managed = Signer(tmp_path / "managed-rights", w.clock)  # writes a real enrollment
    w.fleet.cache._enrollment_path = managed.enrollment_path
    result = attempt(w, envelope(id="dlg-0002"))
    assert (result.code, result.data["rights"], result.data["reason"]) == (
        GateCode.E_UNAUTHORIZED, "missing", "awaiting_managed_set"
    )


def test_broken_enrollment_removes_rights_the_cache_still_holds(tmp_path):
    w = make_world(tmp_path)
    w.fleet.enrollment_path.write_text("{")
    result = attempt(w)
    assert (result.data["rights"], result.data["reason"]) == ("misconfigured", "enrollment_malformed")
    assert w.gate.rights_status()["state"] == "misconfigured"


def test_removed_enrollment_does_not_make_a_managed_device_private(tmp_path):
    w = make_world(tmp_path)
    w.fleet.enrollment_path.unlink()
    result = attempt(w)
    assert (result.data["rights"], result.data["reason"]) == (
        "misconfigured", "managed_set_without_enrollment"
    )


def test_set_for_another_enrollment_is_not_used(tmp_path):
    w = make_world(tmp_path)
    data = json.loads(w.fleet.enrollment_path.read_text())
    data["device_id"] = "another-device"  # re-enrolled as something else
    w.fleet.enrollment_path.write_text(json.dumps(data))
    assert attempt(w).data["reason"] == "set_not_for_this_enrollment"
