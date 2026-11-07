"""Gate 1.1: the EiraSystemAPI family through the same eight layers (ADR-0002).

The power executor talks to a fake busctl here; on the installed system the
VM acceptance test checks that logind answers "yes" to the gate.
"""

from __future__ import annotations

import json

import pytest

from app.gate import Decision, Gate, GateCode
from app.gate.executors import ExecutorRegistry, PowerExecutor
from app.gate.policy import Origin
from app.gate.store import GateStore
from app.gate.system import SYSTEM_SCOPE

ANNE, BO = "did:eira:anne", "did:eira:bo"


class FakeBusctl:
    def __init__(self, can="yes", call_rc=0):
        self.can, self.call_rc, self.calls = can, call_rc, []

    def __call__(self, argv):
        self.calls.append(argv)
        method = argv[4]
        if method.startswith("Can"):
            return 0, f's "{self.can}"'
        return self.call_rc, ""

    @property
    def actions(self):
        return [argv[4] for argv in self.calls if not argv[4].startswith("Can")]


def request(action="poweroff", **overrides):
    req = {
        "eira_system": "1",
        "id": "sys-0001",
        "operation": "power.request_action",
        "input": {"action": action},
        "created_at": "2026-11-07T10:00:00Z",
    }
    req.update(overrides)
    return json.dumps(req)


@pytest.fixture
def sysworld(tmp_path):
    db = str(tmp_path / "gate.db")
    store = GateStore(db)
    store.bind_identity("anne@kommune.dk", ANNE)
    store.bind_identity("bo@kommune.dk", BO)
    store.add_member(SYSTEM_SCOPE, ANNE)
    store.grant_right(ANNE, SYSTEM_SCOPE, "system:power.request_action")
    sessions = {
        "s-anne": {"actor_id": "anne@kommune.dk", "assurance_level": "eid_low"},
        "s-bo": {"actor_id": "bo@kommune.dk", "assurance_level": "eid_high"},
    }
    bus = FakeBusctl()
    registry = ExecutorRegistry()
    registry.register(PowerExecutor(bus))
    gate = Gate(store, registry, sessions=sessions.get)
    return gate, store, bus, sessions


def proposed(gate, raw=None, session="s-anne", origin=Origin.MODEL):
    proposal = gate.propose(raw or request(), session, origin)
    return proposal, proposal.data.get("rendering", {}).get("hash")


def consent_and_confirm(gate, proposal, rhash, session="s-anne"):
    gate.grant_consent(proposal.action_id, proposal.content_hash, rhash, session)
    return gate.confirm(proposal.action_id, proposal.content_hash, rhash, session)


def test_poweroff_goes_through_all_layers_and_is_reported_as_requested(sysworld):
    gate, _store, bus, _ = sysworld
    proposal, rhash = proposed(gate)
    assert proposal.code is GateCode.E_NEED_CONSENT  # irreversible
    assert bus.calls == []  # nothing touched logind before consent
    result = consent_and_confirm(gate, proposal, rhash)
    assert result.decision is Decision.PASS
    assert result.result["visible_state"] == "requested"
    assert bus.actions == ["PowerOff"]
    assert bus.calls[-1][-2:] == ["b", "false"]  # non-interactive: no polkit prompt


def test_the_rendering_says_what_will_happen(sysworld):
    gate, *_ = sysworld
    proposal, _ = proposed(gate)
    assert proposal.data["rendering"]["text"] == (
        "Sluk computeren på denne enhed.\n"
        "Ikke-gemt arbejde i åbne programmer kan gå tabt.\n"
        "Kan ikke fortrydes, når den er udført."
    )
    english = gate.propose(request("suspend", id="sys-en"), "s-anne", Origin.MODEL, "en")
    assert english.data["rendering"]["text"].startswith("Suspend the computer on this device.")


@pytest.mark.parametrize(
    "raw, code",
    [
        (request(operation="power.halt"), GateCode.E_SCHEMA),
        (request("halt"), GateCode.E_SCHEMA),
        (request(rights=["power"]), GateCode.E_SCHEMA),  # a proposal cannot carry rights
        (request(reversibility="idempotent"), GateCode.E_SCHEMA),
        (request(eira_system="2"), GateCode.E_SYNTAX),
        (request(edp="1.0"), GateCode.E_SYNTAX),  # two families at once
        (json.dumps({"eira_system": "1", "id": "x", "operation": "power.request_action"}), GateCode.E_SYNTAX),
        (request(created_at="i morgen"), GateCode.E_SCHEMA),
        (request(input={"action": "poweroff", "force": True}), GateCode.E_SCHEMA),
    ],
)
def test_malformed_or_overreaching_requests_are_rejected(sysworld, raw, code):
    gate, _store, bus, _ = sysworld
    assert gate.propose(raw, "s-anne", Origin.MODEL).code is code
    assert bus.calls == []


def test_without_a_device_right_nothing_happens(sysworld):
    gate, store, bus, _ = sysworld
    store.add_member(SYSTEM_SCOPE, BO)  # Bo uses the device but has no power right
    proposal, rhash = proposed(gate, session="s-bo")
    result = consent_and_confirm(gate, proposal, rhash, session="s-bo")
    assert (result.code, result.layer) == (GateCode.E_UNAUTHORIZED, 6)
    assert bus.actions == []


def test_a_user_who_is_not_on_the_device_is_outside_the_domain(sysworld):
    gate, _store, bus, _ = sysworld
    assert gate.propose(request(), "s-bo", Origin.MODEL).code is GateCode.E_POLICY
    assert bus.calls == []


def test_another_user_cannot_confirm_anne_s_poweroff(sysworld):
    gate, store, bus, _ = sysworld
    store.add_member(SYSTEM_SCOPE, BO)
    store.grant_right(BO, SYSTEM_SCOPE, "system:power.request_action")
    proposal, rhash = proposed(gate)
    gate.grant_consent(proposal.action_id, proposal.content_hash, rhash, "s-anne")
    # The action is bound to Anne: Bo's view of the same request hashes differently.
    result = gate.confirm(proposal.action_id, proposal.content_hash, rhash, "s-bo")
    assert result.decision is Decision.REJECT
    assert bus.actions == []


def test_missing_consent_never_reaches_logind(sysworld):
    gate, _store, bus, _ = sysworld
    proposal, rhash = proposed(gate)
    result = gate.confirm(proposal.action_id, proposal.content_hash, rhash, "s-anne")
    assert result.code is GateCode.E_CONSENT
    assert bus.calls == []


def test_logind_refusing_is_unavailable_and_nothing_happens(sysworld):
    gate, _store, bus, _ = sysworld
    bus.can = "challenge"  # would need interactive auth — a daemon never asks
    proposal, rhash = proposed(gate)
    result = consent_and_confirm(gate, proposal, rhash)
    assert (result.code, result.layer) == (GateCode.E_EXECUTOR_UNAVAILABLE, 8)
    assert bus.actions == []
    assert gate.gate_state("sys-0001") == "pending"


def test_logind_failing_the_call_is_not_success(sysworld):
    gate, _store, bus, _ = sysworld
    bus.call_rc = 1
    proposal, rhash = proposed(gate)
    result = consent_and_confirm(gate, proposal, rhash)
    assert (result.code, result.state) == (GateCode.E_PARTIAL, "failed")


def test_double_confirmation_powers_off_once(sysworld):
    gate, _store, bus, _ = sysworld
    proposal, rhash = proposed(gate)
    first = consent_and_confirm(gate, proposal, rhash)
    second = gate.confirm(proposal.action_id, proposal.content_hash, rhash, "s-anne")
    assert first.execution_id == second.execution_id
    assert bus.actions == ["PowerOff"]


def test_a_crash_during_poweroff_is_unknown_and_never_retried(sysworld, monkeypatch):
    gate, store, bus, sessions = sysworld
    proposal, rhash = proposed(gate)
    monkeypatch.setattr(store, "finish", lambda *a: (_ for _ in ()).throw(SystemExit()))
    with pytest.raises(SystemExit):
        consent_and_confirm(gate, proposal, rhash)
    monkeypatch.undo()
    registry = ExecutorRegistry()
    registry.register(PowerExecutor(bus))
    restarted = Gate(store, registry, sessions=sessions.get)
    assert restarted.gate_state("sys-0001") == "unknown"
    again = restarted.confirm(proposal.action_id, proposal.content_hash, rhash, "s-anne")
    assert again.code is GateCode.E_PARTIAL
    assert bus.actions == ["PowerOff"]  # once, even after the restart


def test_both_families_share_one_audit_chain(sysworld):
    gate, store, *_ = sysworld
    proposed(gate)
    gate.propose('{"edp":"1.0"}', "s-anne", Origin.MODEL)
    entries = [json.loads(row["entry"]) for row in store.audit_entries()]
    assert [e["error"] for e in entries] == ["E_NEED_CONSENT", "E_SYNTAX"]
    assert store.verify_audit_chain()


def test_capabilities_only_ask_logind_never_act(tmp_path):
    from app.gate.ipc import register_gate_handlers
    from tests.test_gate_ipc import FakeServer

    bus = FakeBusctl()
    registry = ExecutorRegistry()
    registry.register(PowerExecutor(bus))
    server = FakeServer()
    register_gate_handlers(server, Gate(GateStore(str(tmp_path / "g.db")), registry, sessions={}.get))
    caps = server.methods["gate.capabilities"]({})
    assert caps["families"] == ["edp", "eira_system"]
    assert caps["power"] == {"poweroff": "yes", "reboot": "yes", "suspend": "yes"}
    assert bus.actions == []


def test_busctl_output_is_parsed_strictly():
    for out, rc, expected in [
        ('s "yes"', 0, "yes"),
        ('s "na"', 0, "na"),
        ("garbage", 0, "error"),
        ('s "yes"', 1, "error"),
    ]:
        executor = PowerExecutor(lambda argv, out=out, rc=rc: (rc, out))
        assert executor.availability("poweroff") == expected


def test_policy_entry_exists_for_every_system_operation():
    from app.gate.policy import REGISTRY, Reversibility
    from app.gate.system import OPERATIONS

    for operation in OPERATIONS:
        assert REGISTRY[f"system:{operation}"].reversibility is Reversibility.IRREVERSIBLE


def test_package_grants_only_the_power_actions():
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    rule = (repo / "packaging/polkit/50-eira-power.rules").read_text()
    granted = sorted(set(__import__("re").findall(r'"(org\.freedesktop\.[a-z0-9.\-]+)"', rule)))
    assert granted == [
        "org.freedesktop.login1.power-off",
        "org.freedesktop.login1.power-off-multiple-sessions",
        "org.freedesktop.login1.reboot",
        "org.freedesktop.login1.reboot-multiple-sessions",
        "org.freedesktop.login1.suspend",
        "org.freedesktop.login1.suspend-multiple-sessions",
    ]
    assert 'subject.user === "eira"' in rule
    assert "ignore-inhibit" not in rule.replace("not the *-ignore-inhibit", "")
    assert "50-eira-power.rules" in (repo / "packaging/debian/rules").read_text()
    profile = (repo / "packaging/apparmor/usr.bin.eira-intentd").read_text()
    assert "member={CanPowerOff,CanReboot,CanSuspend,PowerOff,Reboot,Suspend}" in profile
