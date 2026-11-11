"""The packaged model process (GATE-KERNEL bilag A, AI-INTERFACE-1.0):
proposes only, as its own user, through the gate, under a delegation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.gate import Decision, GateCode
from app.gate import caller as caller_module
from app.gate.caller import acting_as
from app.gate.policy import Origin
from app.ipc.jsonrpc import JsonRpcError
from app.model import daemon
from app.model.contract import (
    E_INVALID_OUTPUT,
    Abstain,
    ConversationContext,
    EdpAction,
    IntentExtraction,
    Participant,
    checked_action,
    checked_extraction,
)
from app.model.rules import RuleAdapter
from tests.callers import HUMAN, MODEL, Peer
from tests.test_gate_kernel import ANNE, BO, CONV
from tests.test_gate_kernel import world as world  # noqa: F401  (fixture)

REPO = Path(__file__).resolve().parents[1]
NOW = "2026-11-11T09:00:00+01:00"
PEOPLE = (Participant(ANNE, "member", "Anne"), Participant(BO, "member", "Bo"))
CTX = ConversationContext(CONV, PEOPLE, NOW)


# --- the rule adapter (EiraLang + EiraAI) -------------------------------------------


def test_a_clear_message_becomes_an_utterance_to_that_person():
    adapter = RuleAdapter()
    intent = adapter.extract_intent("send besked til Bo: Kan du se på budgettet?", CTX, None)
    assert (intent.intent, intent.entities) == ("send_message", {"person": BO, "text": "Kan du se på budgettet?"})
    action = adapter.propose_action(intent, daemon.CANDIDATES, CTX)
    assert (action.type, action.content["text"], action.participants) == ("utterance", "Kan du se på budgettet?",
                                                                           (PEOPLE[1],))


@pytest.mark.parametrize(("when", "iso"), [
    ("2026-11-20 kl 10", "2026-11-20T10:00:00+01:00"),
    ("i morgen kl 13:30", "2026-11-12T13:30:00+01:00"),
])
def test_a_meeting_becomes_a_commitment_proposal(when, iso):
    adapter = RuleAdapter()
    intent = adapter.extract_intent(f"aftal møde med Bo {when} om budgettet", CTX, None)
    action = adapter.propose_action(intent, daemon.CANDIDATES, CTX)
    assert (action.type, action.content) == ("commitment_proposed", {"what": "budgettet", "when": iso})


@pytest.mark.parametrize(("text", "reason"), [
    ("hvad synes du om vejret", "ambiguous_input"),
    ("send besked til Carl: hej", "unknown_person"),       # not in the context
    ("aftal møde med Bo på et tidspunkt om noget", "ambiguous_input"),  # no clear time
    ("aftal møde med Bo i morgen kl 25 om x", "ambiguous_input"),
])
def test_the_adapter_abstains_instead_of_guessing(text, reason):
    assert RuleAdapter().extract_intent(text, CTX, None) == Abstain(reason)


def test_two_people_with_the_same_name_is_ambiguous_not_a_choice():
    ctx = ConversationContext(CONV, PEOPLE + (Participant("did:eira:bo2", "member", "Bo"),), NOW)
    assert RuleAdapter().extract_intent("send besked til Bo: hej", ctx, None) == Abstain("unknown_person")


def test_other_languages_are_an_explicit_error():
    assert RuleAdapter().extract_intent("send a message", CTX, "en").code == "E_UNSUPPORTED_LANGUAGE"


# --- the contract checks (what the process trusts, not the adapter) -------------------


def test_contract_violations_are_never_passed_on():
    assert checked_extraction({"intent": "x"}).code == E_INVALID_OUTPUT
    assert checked_extraction(IntentExtraction("x", {}, "fr", 0.5)).code == E_INVALID_OUTPUT
    assert checked_action(EdpAction("value_transfer", {}), daemon.CANDIDATES, CTX) == Abstain("no_matching_action")
    stranger = EdpAction("utterance", {"text": "hej"}, (Participant("did:eira:mallory", "member"),))
    assert checked_action(stranger, daemon.CANDIDATES, CTX).code == E_INVALID_OUTPUT


# --- the process --------------------------------------------------------------------


class FakeServer:
    def __init__(self):
        self.methods = {}

    def register(self, method, handler):
        self.methods[method] = handler


def prepared(params, as_=HUMAN, adapter=None, sent=None):
    server = FakeServer()
    calls = sent if sent is not None else []

    def propose(envelope, session_id, lang):
        calls.append((envelope, session_id, lang))
        return {"decision": "REJECT", "error": "E_NEED_CONSENT"}

    daemon.register_model_handlers(server, adapter, propose)
    handler = server.methods["model.prepare"]
    assert handler.wants_peer
    return handler({**params, "_peer": Peer(as_)})


REQUEST = {
    "session_id": "s-anne", "conversation_id": CONV, "me": ANNE, "now": NOW,
    "text": "send besked til Bo: Kan du se på budgettet?",
    "participants": [{"identity": ANNE, "role": "member", "name": "Anne"},
                     {"identity": BO, "role": "member", "name": "Bo"}],
}


def test_the_process_proposes_an_edp_envelope_to_the_gate():
    sent = []
    result = prepared(REQUEST, sent=sent)
    [(envelope, session_id, lang)] = sent
    assert (session_id, lang, result["model"]["intent"]) == ("s-anne", "da", "send_message")
    assert envelope["participants"] == [{"identity": ANNE, "role": "member"}, {"identity": BO, "role": "member"}]
    assert envelope["action"] == {"type": "utterance", "content": {"text": "Kan du se på budgettet?", "lang": "da"}}
    # Neutral metadata set by the process, never by the adapter.
    assert envelope["veritas"]["status"] == "unassessed" and envelope["transport"]["degraded"] is False
    assert envelope["temporal"]["supersedes"] is None


def test_an_abstention_reaches_nobody():
    sent = []
    result = prepared({**REQUEST, "text": "hvad synes du?"}, sent=sent)
    assert result["abstain"] == "ambiguous_input" and sent == []


def test_an_unhealthy_adapter_is_not_called():
    class Down(RuleAdapter):
        def health(self):
            return {"ok": False, "detail": "down"}

        def extract_intent(self, *_):
            raise AssertionError("called while unhealthy")

    assert prepared(REQUEST, adapter=Down())["error"] == "E_MODEL_UNAVAILABLE"


def test_the_model_cannot_ask_itself(monkeypatch):
    monkeypatch.setattr(caller_module, "model_uid", lambda: MODEL.uid)
    with pytest.raises(JsonRpcError):
        prepared(REQUEST, as_=MODEL)


@pytest.mark.parametrize("bad", [{"text": ""}, {"text": "x" * 5000}, {"me": None}, {"participants": "x"},
                                 {"session_id": None}])
def test_requests_are_validated(bad):
    with pytest.raises(JsonRpcError):
        prepared({**REQUEST, **bad})


def test_the_process_refuses_to_run_as_anyone_but_eira_model(monkeypatch):
    monkeypatch.setattr(daemon, "model_uid", lambda: None)
    assert daemon.main() == 78
    monkeypatch.setattr(daemon, "model_uid", lambda: 999_999)
    assert daemon.main() == 78


def test_its_socket_lives_in_its_own_runtime_directory(monkeypatch, tmp_path):
    from app.ipc.paths import socket_path

    monkeypatch.setenv("EIRA_MODEL_RUN_DIR", str(tmp_path))
    assert socket_path("modeld") == tmp_path / "modeld.sock"


# --- through the real gate ---------------------------------------------------------


def through_gate(world, session):
    def propose(envelope, session_id, lang):
        with acting_as(MODEL):
            return world.gate.propose(__import__("json").dumps(envelope), session_id, Origin.USER, lang).to_dict()

    server = FakeServer()
    daemon.register_model_handlers(server, None, propose)
    me = ANNE if session == "s-anne" else BO
    return server.methods["model.prepare"]({**REQUEST, "session_id": session, "me": me, "_peer": Peer(HUMAN)})


def test_under_anne_s_delegation_the_proposal_waits_for_her_consent(world, monkeypatch):
    monkeypatch.setattr(caller_module, "model_uid", lambda: MODEL.uid)
    result = through_gate(world, "s-anne")
    gate = result["gate"]
    # The gate saw the model (SO_PEERCRED), whatever origin the call claimed.
    assert gate["error"] == GateCode.E_NEED_CONSENT.value, gate
    record = world.store.find(gate["action_id"])
    assert record["origin"] == "model" and record["state"] == "pending"


def test_without_a_delegation_the_gate_refuses_the_model(world, monkeypatch):
    monkeypatch.setattr(caller_module, "model_uid", lambda: MODEL.uid)
    world.store.add_member(CONV, BO)
    gate = through_gate(world, "s-bo")["gate"]
    assert gate["decision"] == Decision.REJECT.value and gate["error"] == GateCode.E_UNAUTHORIZED.value


# --- packaging ----------------------------------------------------------------------


def test_the_unit_isolates_the_model():
    unit = (REPO / "packaging/model/eira-modeld.service").read_text()
    for line in ("User=eira-model", "PrivateNetwork=true", "RestrictAddressFamilies=AF_UNIX",
                 "ProtectSystem=strict", "NoNewPrivileges=true", "CapabilityBoundingSet=\n",
                 "InaccessiblePaths=-/data", "RuntimeDirectory=eira-model", "AppArmorProfile=/usr/bin/eira-modeld"):
        assert line in unit, line
    assert "Group=eira\n" not in unit and "SupplementaryGroups" not in unit


def test_apparmor_lets_it_reach_only_the_gate():
    profile = (REPO / "packaging/model/usr.bin.eira-modeld").read_text()
    assert "/run/eira/intentd.sock rw," in profile
    assert "/run/eira/*.sock" not in profile
    for denied in ("deny /data/** rwklx,", "deny network inet,", "deny @{HOME}/** rwklx,",
                   "deny /run/eira/{stated,identityd,fleetd,veritasd,graphd,delegationd}.sock rw,"):
        assert denied in profile


def test_the_package_installs_and_enables_it():
    rules = (REPO / "packaging/debian/rules").read_text()
    postinst = (REPO / "packaging/debian/postinst").read_text()
    assert "packaging/bin/eira-modeld debian/eira-os-core/usr/bin/eira-modeld" in rules
    assert "packaging/model/eira-modeld.service" in rules and "packaging/model/usr.bin.eira-modeld" in rules
    assert "systemctl enable eira-modeld.service" in postinst
