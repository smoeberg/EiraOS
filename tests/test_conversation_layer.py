"""EIRA-CONVERSATION-1.0: membership comes only from recorded events, and the
event stream shows each user exactly the conversations they can see.

The fixture is production-shaped: no membership is inserted by hand. Rights
come from a Fleet set that grants every authenticated user the gate's actions
on ``obj:sag:*``, like the bundled default set.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time

import pytest

from app.conversation import feed
from app.conversation.ipc import METHODS, NO_SESSION, UNKNOWN_CONVERSATION, register_conversation_handlers
from app.gate import Decision, Gate, GateCode
from app.gate import caller as caller_module
from app.gate.caller import acting_as
from app.gate.executors import default_registry
from app.gate.policy import Origin
from app.gate.store import GateStore
from tests.callers import HUMAN, HUMAN_SESSION, MODEL, OTHER_HUMAN, Peer, ProvingGate
from tests.rights_helpers import TestFleet
from tests.test_gate_kernel import BootClock, Clock, envelope, raw

CONV = "obj:sag:42"
ANNE, BO, CARL = "did:eira:anne", "did:eira:bo", "did:eira:carl"


@pytest.fixture(autouse=True)
def _fresh_notifier(monkeypatch):
    monkeypatch.setattr(feed, "NOTIFIER", feed.Notifier())


@pytest.fixture
def world(tmp_path):
    db = str(tmp_path / "gate.db")
    store = GateStore(db)
    sessions = {
        "s-anne": {**HUMAN_SESSION, "actor_id": "anne", "identity": ANNE, "assurance_level": "eid_low"},
        "s-bo": {**HUMAN_SESSION, "actor_id": "bo", "identity": BO, "assurance_level": "eid_low"},
        "s-carl": {**HUMAN_SESSION, "actor_id": "carl", "identity": CARL, "assurance_level": "eid_low"},
    }
    clock, boot = Clock(), BootClock()
    fleet = TestFleet(tmp_path / "rights", clock, boot_clock=boot)
    fleet.grant("obj:sag:*").publish()  # every authenticated user, every gate action
    gate = ProvingGate(
        Gate(store, default_registry(db), sessions=sessions.get, clock=clock, boot_clock=boot, rights=fleet.cache),
        sessions.get,
    )

    class World:
        pass

    w = World()
    w.db, w.store, w.gate, w.sessions = db, store, gate, sessions
    return w


def participants(*pairs):
    return [{"identity": identity, "role": role} for identity, role in pairs]


def send(world, session, env):
    """Propose, consent and confirm as the given user, like the app does."""
    proposal = world.gate.propose(raw(env), session, Origin.USER)
    if proposal.code is GateCode.E_NEED_CONSENT:
        rhash = proposal.data["rendering"]["hash"]
        world.gate.grant_consent(env["id"], proposal.content_hash, rhash, session)
    elif proposal.decision is not None:
        return proposal
    rhash = world.store.find(env["id"])["rendering_hash"]
    return world.gate.confirm(env["id"], proposal.content_hash, rhash, session)


def meeting(id="dlg-1", conversation=CONV, people=None):
    return envelope(
        id=id,
        conversation_id=conversation,
        participants=people or participants((ANNE, "member"), (BO, "member"), ("external:sms:+4512345678", "member")),
    )


def answer(id, to, by, kind="commitment_accepted"):
    return envelope(kind, {"commitment_id": to}, id=id, participants=participants((by, "member")))


def roles(world, conversation=CONV):
    with sqlite3.connect(world.db) as conn:
        return dict(conn.execute(
            "SELECT identity, role FROM gate_members WHERE conversation_id = ?", (conversation,)
        ).fetchall())


def stream(world, identity, cursor=0):
    with sqlite3.connect(world.db) as conn:
        return feed.since(conn, identity, cursor)


# --- membership (§3) ----------------------------------------------------------------


def test_an_installed_machine_starts_with_no_members_and_the_first_event_opens_the_conversation(world):
    assert roles(world) == {}
    result = send(world, "s-anne", meeting())
    assert result.decision is Decision.PASS, result
    # The local identities addressed as members join; an external address does not.
    assert roles(world) == {ANNE: "member", BO: "member"}
    assert result.result["seq"] == 1


def test_others_cannot_act_in_a_conversation_they_are_not_part_of(world):
    send(world, "s-anne", meeting(people=participants((ANNE, "member"))))
    intruder = envelope(id="dlg-carl", participants=participants((CARL, "member")))
    result = world.gate.propose(raw(intruder), "s-carl", Origin.USER)
    assert (result.code, result.layer) == (GateCode.E_POLICY, 4)
    assert "not a member" in result.detail


def test_an_addressed_participant_joins_and_can_answer(world):
    send(world, "s-anne", meeting())
    assert [c["event_id"] for c in feed.awaiting(sqlite3.connect(world.db), BO)["commitments"]] == ["dlg-1"]
    # Anne proposed it: it waits for Bo, not for her.
    assert feed.awaiting(sqlite3.connect(world.db), ANNE)["commitments"] == []
    result = send(world, "s-bo", answer("dlg-2", "dlg-1", BO))
    assert result.decision is Decision.PASS, result
    assert feed.awaiting(sqlite3.connect(world.db), BO)["commitments"] == []


def test_an_observer_sees_but_cannot_act(world):
    send(world, "s-anne", meeting(people=participants((ANNE, "member"), (CARL, "observer"))))
    assert roles(world)[CARL] == "observer"
    assert [e["event_id"] for e in stream(world, CARL)["events"]] == ["dlg-1"]
    reply = envelope("utterance", {"text": "Jeg kommer"}, id="dlg-c", participants=participants((CARL, "member")))
    result = world.gate.propose(raw(reply), "s-carl", Origin.USER)
    assert (result.code, result.layer) == (GateCode.E_POLICY, 4)
    assert "observer" in result.detail
    # Nothing waits for an observer.
    assert feed.awaiting(sqlite3.connect(world.db), CARL)["commitments"] == []


def test_membership_only_grows(world):
    send(world, "s-anne", meeting(people=participants((ANNE, "member"), (BO, "observer"))))
    # Addressing Bo as a member promotes him; nothing can demote or remove.
    send(world, "s-anne", envelope("utterance", {"text": "Bo, kan du tage den?"}, id="dlg-2",
                                   participants=participants((ANNE, "member"), (BO, "member"))))
    assert roles(world)[BO] == "member"
    send(world, "s-anne", envelope("utterance", {"text": "Tak"}, id="dlg-3",
                                   participants=participants((ANNE, "member"), (BO, "observer"))))
    assert roles(world) == {ANNE: "member", BO: "member"}


def test_two_users_cannot_both_open_the_same_new_conversation(world, monkeypatch):
    """The domain is checked again inside the executor's transaction."""
    anne = meeting("dlg-a", people=participants((ANNE, "member")))
    carl = meeting("dlg-c", people=participants((CARL, "member")))
    # Carl gets past lag 4 while the conversation is still unclaimed …
    proposal = world.gate.propose(raw(carl), "s-carl", Origin.USER)
    rhash = proposal.data["rendering"]["hash"]
    world.gate.grant_consent("dlg-c", proposal.content_hash, rhash, "s-carl")
    send(world, "s-anne", anne)
    # … and lag 4 at confirm is made to miss it, as in a race.
    monkeypatch.setattr(world.store, "check_domain", lambda *_: None)
    result = world.gate.confirm("dlg-c", proposal.content_hash, rhash, "s-carl")
    assert result.code is GateCode.E_EXECUTOR_UNAVAILABLE, result
    assert world.store.find("dlg-c")["state"] == "pending"  # nothing happened
    assert roles(world) == {ANNE: "member"}
    assert [e["event_id"] for e in stream(world, CARL)["events"]] == []


def test_feed_outbox_and_membership_are_written_together_or_not_at_all(world):
    with sqlite3.connect(world.db) as conn:  # an outbox row that will collide
        conn.execute(
            "INSERT INTO conversation_outbox (event_id, conversation_id, action_type, envelope, execution_id,"
            " delivery_state, recorded_at) VALUES ('dlg-1', 'obj:sag:7', 'utterance', '{}', 'x', 'pending', 'now')"
        )
    result = send(world, "s-anne", meeting())
    assert result.decision is not Decision.PASS
    with sqlite3.connect(world.db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM conversation_feed").fetchone()[0] == 0
    assert roles(world) == {}


def test_the_feed_is_append_only(world):
    send(world, "s-anne", meeting())
    with sqlite3.connect(world.db) as conn:
        for statement in ("UPDATE conversation_feed SET author = 'x'", "DELETE FROM conversation_feed"):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(statement)


# --- the stream (§4) -----------------------------------------------------------------


def test_each_user_sees_only_conversations_they_can_see(world):
    send(world, "s-anne", meeting())
    send(world, "s-carl", meeting("dlg-x", conversation="obj:sag:7", people=participants((CARL, "member"))))
    anne = stream(world, ANNE)
    assert [e["event_id"] for e in anne["events"]] == ["dlg-1"]
    # The cursor moves past Carl's event without revealing it.
    assert anne["cursor"] == 2
    assert stream(world, ANNE, anne["cursor"])["events"] == []
    first = anne["events"][0]
    assert (first["author"], first["delivery"], first["type"]) == (ANNE, "pending", "commitment_proposed")


def test_a_new_member_sees_the_history_of_the_object(world):
    send(world, "s-anne", meeting(people=participants((ANNE, "member"))))
    send(world, "s-anne", envelope("utterance", {"text": "Carl, se her"}, id="dlg-2",
                                   participants=participants((ANNE, "member"), (CARL, "member"))))
    with sqlite3.connect(world.db) as conn:
        assert [e["event_id"] for e in feed.history(conn, CARL, CONV, None)] == ["dlg-2", "dlg-1"]
        assert feed.history(conn, BO, CONV, None) is None


def test_long_poll_wakes_when_an_event_is_recorded(world):
    def later():
        time.sleep(0.2)
        with acting_as(HUMAN):
            send(world, "s-anne", meeting())

    thread = threading.Thread(target=later)
    started = time.monotonic()
    thread.start()
    feed.NOTIFIER.wait_beyond(0, 5)
    assert time.monotonic() - started < 3
    thread.join()
    assert stream(world, ANNE)["events"]


# --- over the socket (§5) ------------------------------------------------------------


class FakeServer:
    def __init__(self):
        self.methods = {}

    def register(self, method, handler):
        self.methods[method] = handler


def call(server, method, params, as_):
    handler = server.methods[method]
    assert handler.wants_peer
    return handler({**params, "_peer": Peer(as_)})


@pytest.fixture
def server(world):
    srv = FakeServer()
    register_conversation_handlers(srv, world.gate._gate)
    return srv


def test_only_reads_are_exposed(server):
    assert set(server.methods) == set(METHODS)
    assert not any(word in m for m in METHODS for word in ("add", "join", "set", "write", "remove"))


def test_the_stream_needs_the_user_s_own_session(world, server, monkeypatch):
    from app.ipc.jsonrpc import JsonRpcError

    send(world, "s-anne", meeting())
    assert call(server, "events.since", {"session_id": "s-anne"}, HUMAN)["events"]
    for params, who in (({"session_id": "s-anne"}, OTHER_HUMAN), ({}, HUMAN), ({"session_id": "nope"}, HUMAN)):
        with pytest.raises(JsonRpcError) as error:
            call(server, "events.since", params, who)
        assert error.value.code == NO_SESSION
    monkeypatch.setattr(caller_module, "model_uid", lambda: MODEL.uid)
    with pytest.raises(JsonRpcError) as error:
        call(server, "events.since", {"session_id": "s-anne"}, MODEL)
    assert error.value.code == NO_SESSION  # the model cannot read the stream


def test_a_hidden_conversation_looks_like_a_missing_one(world, server):
    from app.ipc.jsonrpc import JsonRpcError

    send(world, "s-anne", meeting(people=participants((ANNE, "member"))))
    answers = []
    for conversation in (CONV, "obj:sag:404"):
        for method in ("conversation.events", "conversation.members"):
            with pytest.raises(JsonRpcError) as error:
                call(server, method, {"session_id": "s-carl", "conversation_id": conversation}, HUMAN)
            answers.append((error.value.code, error.value.message))
    assert set(answers) == {(UNKNOWN_CONVERSATION, "unknown conversation")}


def test_conversation_list_members_and_awaiting(world, server):
    send(world, "s-anne", meeting())
    listed = call(server, "conversation.list", {"session_id": "s-bo"}, HUMAN)["conversations"]
    assert [(c["conversation_id"], c["role"], c["members"]) for c in listed] == [(CONV, "member", 2)]
    members = call(server, "conversation.members", {"session_id": "s-bo", "conversation_id": CONV}, HUMAN)
    assert members["members"] == [{"identity": ANNE, "role": "member"}, {"identity": BO, "role": "member"}]
    waiting = call(server, "conversation.awaiting", {"session_id": "s-bo"}, HUMAN)
    assert [c["event_id"] for c in waiting["commitments"]] == ["dlg-1"]


def test_a_pending_model_proposal_waits_for_the_user_s_decision(world, server, monkeypatch):
    send(world, "s-anne", meeting())
    monkeypatch.setattr(caller_module, "model_uid", lambda: MODEL.uid)
    with acting_as(MODEL):
        world.gate.propose(raw(envelope("utterance", {"text": "Udkast"}, id="dlg-m",
                                        participants=participants((ANNE, "member")))), "s-anne", Origin.MODEL)
    waiting = call(server, "conversation.awaiting", {"session_id": "s-anne"}, HUMAN)
    [decision] = waiting["decisions"]
    assert (decision["action_id"], decision["origin"]) == ("dlg-m", "model")
    assert "Udkast" in decision["rendering"]["text"]


def test_long_poll_over_the_socket_returns_after_the_wait(world, server, monkeypatch):
    started = time.monotonic()
    page = call(server, "events.since", {"session_id": "s-anne", "wait_ms": 200}, HUMAN)
    assert page["events"] == [] and time.monotonic() - started >= 0.15
    monkeypatch.setattr(feed, "MAX_WAIT_S", 0.3)
    started = time.monotonic()
    page = call(server, "events.since", {"session_id": "s-anne", "wait_ms": 10**9, "cursor": 10**6}, HUMAN)
    assert time.monotonic() - started < 2
    assert page["events"] == []  # capped wait, no error


def test_parameters_are_validated(server):
    from app.ipc.jsonrpc import JsonRpcError

    for params in ({"cursor": -1}, {"cursor": "1"}, {"limit": True}):
        with pytest.raises(JsonRpcError):
            call(server, "events.since", {"session_id": "s-anne", **params}, HUMAN)


def test_events_are_json_serialisable(world, server):
    send(world, "s-anne", meeting())
    json.dumps(call(server, "events.since", {"session_id": "s-anne"}, HUMAN))
