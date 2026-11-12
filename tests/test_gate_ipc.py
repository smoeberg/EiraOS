"""Gate Kernel over intentd's JSON-RPC: the only IPC way to execute is gate.confirm."""

import json

import pytest

from app.gate.executors import default_registry
from app.gate.ipc import register_gate_handlers
from app.gate.kernel import Gate
from app.gate.store import GateStore, utc_now
from app.ipc.jsonrpc import JsonRpcError
from tests.callers import HUMAN, HUMAN_SESSION, Peer
from tests.rights_helpers import TestFleet
from tests.test_gate_kernel import ANNE, CONV, envelope


class FakeServer:
    """Calls handlers the way the daemon server does, including the caller
    from SO_PEERCRED for handlers that want it."""

    def __init__(self, caller=HUMAN):
        self.methods = {}
        self.caller = caller

    def register(self, name, handler):
        if getattr(handler, "wants_peer", False):
            inner = handler

            def handler(params, _inner=inner):
                return _inner({**params, "_peer": Peer(self.caller) if self.caller else None})

        self.methods[name] = handler


@pytest.fixture
def rpc(tmp_path):
    db = str(tmp_path / "gate.db")
    store = GateStore(db)
    store.bind_identity("anne@kommune.dk", ANNE)
    store.add_member(CONV, ANNE)
    fleet = TestFleet(tmp_path / "rights", utc_now)
    fleet.grant(CONV, principal=ANNE).publish()
    sessions = {"s-anne": {**HUMAN_SESSION, "actor_id": "anne@kommune.dk", "assurance_level": "eid_low"}}
    server = FakeServer()
    register_gate_handlers(server, Gate(store, default_registry(db), sessions=sessions.get, rights=fleet.cache))
    return server.methods


def test_full_flow_over_ipc(rpc):
    proposal = rpc["gate.propose"]({"session_id": "s-anne", "edp": envelope(), "origin": "model"})
    assert proposal["error"] == "E_NEED_CONSENT" and proposal["state"] == "pending"
    rendering = proposal["data"]["rendering"]
    assert rendering["lang"] == "da" and rendering["text"].startswith("Foreslå «Møde om budgettet»")
    args = {
        "session_id": "s-anne",
        "action_id": "dlg-0001",
        "content_hash": proposal["content_hash"],
        "rendering_hash": rendering["hash"],
    }
    from app.gate import consent_proof
    from tests.callers import CONSENT_KEY, HUMAN

    def prove(verb):
        return consent_proof.compute(CONSENT_KEY, verb, HUMAN.uid, "s-anne", args["action_id"],
                                     args["content_hash"], args["rendering_hash"])

    assert rpc["gate.consent"](args)["error"] == "E_CONSENT_PROOF"  # no proof: not from the app
    assert rpc["gate.consent"]({**args, "proof": prove("consent")})["detail"] == "consent recorded"
    assert rpc["gate.confirm"]({**args, "proof": prove("consent")})["error"] == "E_CONSENT_PROOF"  # wrong verb
    done = rpc["gate.confirm"]({**args, "proof": prove("confirm")})
    assert done["decision"] == "PASS" and done["result"]["visible_state"] == "proposed"
    assert rpc["gate.status"]({"action_id": "dlg-0001", "session_id": "s-anne"})["state"] == "executed"
    json.dumps(done)  # serialisable for the wire


def test_no_ipc_method_reaches_an_executor_directly(rpc):
    assert set(rpc) == {"gate.propose", "gate.consent", "gate.confirm", "gate.status", "gate.capabilities",
                        "gate.rendering"}


def test_bad_parameters(rpc):
    assert rpc["gate.propose"]({"session_id": "s-anne"})["error"] == "E_SYNTAX"
    with pytest.raises(JsonRpcError):
        rpc["gate.propose"]({"session_id": "s-anne", "edp": envelope(), "origin": "admin"})
    with pytest.raises(JsonRpcError):
        rpc["gate.confirm"]({"session_id": "s-anne"})
    with pytest.raises(JsonRpcError):
        rpc["gate.status"]({"action_id": "nope"})


def test_intentd_registers_the_gate():
    from app.daemons.intentd import IntentDaemonService, register_intent_handlers

    server = FakeServer()
    register_intent_handlers(server, IntentDaemonService.__new__(IntentDaemonService))
    assert {"gate.propose", "gate.consent", "gate.confirm", "gate.status", "gate.capabilities"} <= set(server.methods)


# Every method intentd exposes, classified. A new method fails this test until
# someone decides which class it belongs to. KNOWN_BYPASSES are write paths
# that do not go through the gate yet (spec Bilag A, limitation 5); the next
# PR redirects them to E_GATE_REQUIRED and empties this set.
GATE_METHODS = {"gate.propose", "gate.consent", "gate.confirm", "gate.status", "gate.capabilities", "gate.rendering"}
READ_ONLY = {
    "health",
    "dashboard.get",
    "intent.parse",
    "intent.plan",
    "journey.list",
    "journey.get",
    "capability.list",
    "presentation.mode_get",
    # Conversation layer: reads for an authenticated human session only.
    "events.since",
    "conversation.list",
    "conversation.events",
    "conversation.members",
    "conversation.awaiting",
}
POLICY_GATED_SETTINGS = {"presentation.mode_set"}  # Builder needs device policy
# Former bypasses, now answering E_GATE_REQUIRED (proved below).
REDIRECTED = {"intent.confirm", "intent.execute", "journey.advance"}
KNOWN_BYPASSES: set[str] = set()


def test_every_intentd_method_is_classified():
    from app.daemons.intentd import IntentDaemonService, register_intent_handlers

    server = FakeServer()
    register_intent_handlers(server, IntentDaemonService.__new__(IntentDaemonService))
    exposed = set(server.methods)
    classified = GATE_METHODS | READ_ONLY | POLICY_GATED_SETTINGS | REDIRECTED | KNOWN_BYPASSES
    assert exposed == classified, {
        "unclassified": sorted(exposed - classified),
        "gone": sorted(classified - exposed),
    }


def test_former_bypasses_answer_gate_required_and_never_execute(monkeypatch, tmp_path):
    """Over the real JSON-RPC server: no former write path can reach the
    stated appender. The old executor and journey writer no longer exist."""
    from app.daemons.base import JsonRpcServer
    from app.daemons.intentd import IntentDaemonService, register_intent_handlers
    from app.gate.ipc import GATE_REQUIRED

    touched = []
    service = IntentDaemonService.__new__(IntentDaemonService)
    monkeypatch.setattr(service, "execute", lambda *a, **k: touched.append("stated_append"), raising=False)
    server = JsonRpcServer(name="intent-test", daemon="intentd")
    register_intent_handlers(server, service)
    payloads = {
        "intent.confirm": {"intent_id": "i-1", "session_id": "s-1"},
        "intent.execute": {"intent": "Godkend bevilling på 175.000 kr"},
        "journey.advance": {"journey_id": "j-1"},
    }
    for method, params in payloads.items():
        request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        response = json.loads(server.handle_line(json.dumps(request)))
        assert response["error"]["code"] == GATE_REQUIRED, method
        assert response["error"]["data"]["use"] == "gate.propose"
        assert response["error"]["data"]["user_message"]
    assert touched == []
