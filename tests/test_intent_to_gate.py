"""F1b (UDVIKLINGSPLAN): the first whole path, in process.

The IntentBar's text goes to the model process, which proposes to the real
gate as itself; the gate wants a delegation from the human, then her
consent and confirmation (the consent agent's job), and only then asks
logind. The VM test of the same path needs an installed login (F0.3) and a
graphical session (F0.2); until then this is where the chain is proven.
"""

from __future__ import annotations

import json

import pytest

from app.auth.delegation import (
    DelegationCreateRequest,
    DelegationRepository,
    DelegationScope,
    DelegationService,
)
from app.gate import Decision, Gate, GateCode
from app.gate import caller as caller_module
from app.gate.caller import acting_as, model_identity
from app.gate.executors import ExecutorRegistry, PowerExecutor
from app.gate.policy import Origin
from app.gate.store import GateStore, utc_now
from app.gate.system import SYSTEM_SCOPE
from app.model import daemon
from app.model.rules import RuleAdapter
from tests.callers import HUMAN, HUMAN_SESSION, MODEL, Peer, ProvingGate
from tests.rights_helpers import TestFleet
from tests.test_gate_system import FakeBusctl
from tests.test_model_process import FakeServer

ANNE = "did:eira:anne"
TARGET = "intent:system:power.request_action"


@pytest.fixture
def chain(tmp_path, monkeypatch):
    monkeypatch.setattr(caller_module, "model_uid", lambda: MODEL.uid)
    # modeld names itself as the gate does: the model's own UID.
    monkeypatch.setattr(daemon, "_own_identity", lambda: model_identity(MODEL))
    store = GateStore(str(tmp_path / "gate.db"))
    store.bind_identity("anne@kommune.dk", ANNE)
    store.add_member(SYSTEM_SCOPE, ANNE)
    fleet = TestFleet(tmp_path / "rights", utc_now)
    fleet.grant(SYSTEM_SCOPE, ["system:power.request_action"], principal=ANNE).publish()
    sessions = {"s-anne": {**HUMAN_SESSION, "actor_id": "anne@kommune.dk", "assurance_level": "eid_low"}}
    bus = FakeBusctl()
    registry = ExecutorRegistry()
    registry.register(PowerExecutor(bus))
    delegations = DelegationService(DelegationRepository(tmp_path / "app.db"))
    monkeypatch.setattr(delegations, "_audit", lambda *a, **k: None)
    gate = ProvingGate(Gate(store, registry, sessions=sessions.get, rights=fleet.cache,
                            delegations=delegations), sessions.get)

    def propose(envelope, session_id, lang):
        # What modeld's IPC call does: the gate sees the model's UID.
        with acting_as(MODEL):
            return gate.propose(json.dumps(envelope), session_id, Origin.USER, lang).to_dict()

    server = FakeServer()
    daemon.register_model_handlers(server, RuleAdapter(), propose)

    def ask(text):  # the IntentBar: no conversation, only the session
        return server.methods["model.prepare"]({
            "session_id": "s-anne", "text": text, "now": "2026-11-13T09:00:00+01:00", "_peer": Peer(HUMAN)})

    def delegate(target=TARGET):  # what the consent agent does after the user says yes
        delegations.create_delegation(ANNE, DelegationCreateRequest(
            delegee_id=model_identity(MODEL), scope=DelegationScope(actions=["prepare"], targets=[target])))

    class Chain:
        pass

    c = Chain()
    c.gate, c.store, c.bus, c.ask, c.delegate = gate, store, bus, ask, delegate
    return c


def test_a_power_command_without_a_delegation_says_which_one_is_missing(chain):
    reply = chain.ask("sluk computeren")
    gate = reply["gate"]
    assert gate["decision"] == Decision.REJECT.value and gate["error"] == GateCode.E_UNAUTHORIZED.value
    assert reply["action_type"] == "system:power.request_action"
    assert reply["needs_delegation"] == {"delegee_id": model_identity(MODEL), "target": TARGET}
    assert chain.bus.calls == []


def test_the_whole_path_from_text_to_logind(chain):
    chain.delegate()
    reply = chain.ask("sluk computeren")
    gate = reply["gate"]
    # Irreversible: the gate holds it for the human's consent; nothing ran.
    assert gate["error"] == GateCode.E_NEED_CONSENT.value and gate["state"] == "pending", gate
    assert "needs_delegation" not in reply
    assert chain.bus.calls == []
    record = chain.store.find(gate["action_id"])
    assert record["origin"] == "model"

    # The consent agent: consent, then confirm, as the human (her UID).
    rhash = gate["data"]["rendering"]["hash"]
    with acting_as(HUMAN):
        consented = chain.gate.grant_consent(gate["action_id"], gate["content_hash"], rhash, "s-anne")
        assert consented.code is None, consented.to_dict()
        done = chain.gate.confirm(gate["action_id"], gate["content_hash"], rhash, "s-anne")
    assert done.decision is Decision.PASS, done.to_dict()
    assert done.result["visible_state"] == "requested"
    assert chain.bus.actions == ["PowerOff"]
    with acting_as(HUMAN):
        assert chain.gate.status(gate["action_id"], "s-anne")["state"] == "executed"


def test_the_model_cannot_consent_for_her(chain):
    chain.delegate()
    gate = chain.ask("genstart")["gate"]
    rhash = gate["data"]["rendering"]["hash"]
    with acting_as(MODEL):
        refused = chain.gate.grant_consent(gate["action_id"], gate["content_hash"], rhash, "s-anne")
    assert refused.decision is Decision.REJECT
    assert chain.bus.calls == []


@pytest.mark.parametrize("text, action", [
    ("sluk computeren", "poweroff"), ("Sluk maskinen.", "poweroff"), ("luk ned", "poweroff"),
    ("genstart", "reboot"), ("genstart pc'en", "reboot"),
    ("sæt computeren i dvale", "suspend"), ("dvale", "suspend"),
])
def test_power_commands_the_model_understands(chain, text, action):
    chain.delegate()
    gate = chain.ask(text)["gate"]
    record = chain.store.find(gate["action_id"])
    assert record["action_type"] == "system:power.request_action"
    assert json.loads(record["raw"])["input"] == {"action": action}


@pytest.mark.parametrize("text", ["sluk lyset", "sluk computeren i morgen", "hvad er klokken", "genstart routeren"])
def test_anything_else_is_an_honest_abstention(chain, text):
    reply = chain.ask(text)
    assert reply["abstain"] == "ambiguous_input"
    assert "gate" not in reply and chain.bus.calls == []


def test_without_a_conversation_the_model_proposes_no_message(chain):
    chain.delegate("intent:*")
    reply = chain.ask("send besked til Bo: hej")
    # No conversation, no person to address: abstain, never a guess.
    assert "gate" not in reply
