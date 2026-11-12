"""Process identity at the gate (GATE-KERNEL bilag A pkt. 1).

The caller comes from SO_PEERCRED, never from the request. The model runs as
its own user: it can propose, but never consent or confirm, and its
proposals are origin `model` whatever it claims. A session counts only if it
was authenticated, and only for the uid it was bound to at login."""

from __future__ import annotations

import json
import socket
import threading

import pytest

from app.daemons.base import JsonRpcServer
from app.gate import Decision, GateCode
from app.gate import caller as caller_module
from app.gate.caller import acting_as
from app.gate.ipc import register_gate_handlers
from app.gate.policy import Origin
from app.ipc.access import caller, read
from tests.callers import HUMAN, MODEL, OTHER_HUMAN, Peer
from tests.test_gate_ipc import FakeServer
from tests.test_gate_kernel import envelope, propose_and_consent, raw, rh
from tests.test_gate_kernel import world as world  # noqa: F401  (fixture)


def assert_no_actor(result, world, action_id="dlg-0001"):
    """No actor is rejected before anything is stored: in layer 4 (outside
    any user's domain) or layer 6 (unauthorized)."""
    assert result.decision is Decision.REJECT
    assert result.code in {GateCode.E_POLICY, GateCode.E_UNAUTHORIZED}
    assert world.store.find(action_id) is None


def test_without_a_caller_there_is_no_actor(world):
    with acting_as(None):
        result = world.gate.propose(raw(envelope()), "s-anne", Origin.USER)
    assert_no_actor(result, world)


def test_model_can_propose_but_never_consent(world):
    with acting_as(MODEL):
        proposal = world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL)
        assert proposal.code is GateCode.E_NEED_CONSENT
        consent = world.gate.grant_consent(
            "dlg-0001", proposal.content_hash, rh(world, "dlg-0001"), "s-anne"
        )
    assert consent.code is GateCode.E_MODEL_CANNOT_DECIDE


def test_model_cannot_confirm_what_the_user_consented_to(world):
    env, digest = propose_and_consent(world)  # as the human
    with acting_as(MODEL):
        result = world.gate.confirm(env["id"], digest, rh(world, env["id"]), "s-anne")
    assert result.code is GateCode.E_MODEL_CANNOT_DECIDE
    assert world.gate.status(env["id"], "s-anne")["state"] == "pending"


def test_model_proposes_and_the_human_decides(world):
    with acting_as(MODEL):
        proposal = world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL)
    consent = world.gate.grant_consent("dlg-0001", proposal.content_hash, rh(world, "dlg-0001"), "s-anne")
    assert (consent.code, consent.state) == (None, "pending")
    result = world.gate.confirm("dlg-0001", proposal.content_hash, rh(world, "dlg-0001"), "s-anne")
    assert result.decision is Decision.PASS


def test_another_os_user_cannot_use_the_session(world):
    env, digest = propose_and_consent(world)
    with acting_as(OTHER_HUMAN):
        assert_no_actor(world.gate.propose(raw(envelope(id="dlg-0002")), "s-anne", Origin.USER), world, "dlg-0002")
        assert world.gate.confirm(env["id"], digest, rh(world, env["id"]), "s-anne").decision is Decision.REJECT
        assert world.gate.status(env["id"], "s-anne") is None
    assert world.gate.status(env["id"], "s-anne")["state"] == "pending"


@pytest.mark.parametrize("missing", ["authenticated_at", "os_uid"])
def test_unauthenticated_or_unbound_session_is_no_session(world, missing):
    world.sessions["s-anne"].pop(missing)
    assert_no_actor(world.gate.propose(raw(envelope()), "s-anne", Origin.USER), world)


# --- over IPC ---------------------------------------------------------------------


@pytest.fixture
def model_uid_990(monkeypatch):
    monkeypatch.setattr(caller_module, "model_uid", lambda: MODEL.uid)


def _rpc(world, caller):
    server = FakeServer(caller)
    register_gate_handlers(server, world.gate)
    return server.methods


def test_model_claiming_user_origin_is_recorded_as_model(world, model_uid_990):
    methods = _rpc(world, MODEL)
    methods["gate.propose"]({"edp": envelope(), "session_id": "s-anne", "origin": "user"})
    assert world.store.find("dlg-0001")["origin"] == "model"


def test_model_over_ipc_cannot_consent(world, model_uid_990):
    proposal = _rpc(world, MODEL)["gate.propose"]({"edp": envelope(), "session_id": "s-anne"})
    consent = _rpc(world, MODEL)["gate.consent"]({
        "action_id": "dlg-0001", "content_hash": proposal["content_hash"],
        "rendering_hash": rh(world, "dlg-0001"), "session_id": "s-anne",
    })
    assert (consent["decision"], consent["error"]) == ("REJECT", "E_MODEL_CANNOT_DECIDE")
    assert "only the user" in consent["detail"]


def test_ipc_without_peer_fails_closed(world):
    proposal = _rpc(world, None)["gate.propose"]({"edp": envelope(), "session_id": "s-anne"})
    assert proposal["decision"] == "REJECT" and world.store.find("dlg-0001") is None


def test_model_is_recognised_by_uid(monkeypatch):
    monkeypatch.setattr(caller_module, "model_uid", lambda: 990)
    assert caller_module.from_peer(Peer(MODEL)).model is True
    assert caller_module.from_peer(Peer(HUMAN)).model is False
    monkeypatch.setattr(caller_module, "model_uid", lambda: None)  # no model user installed
    assert caller_module.from_peer(Peer(MODEL)).model is False


# --- the daemon server ---------------------------------------------------------------


def _server_with(handler):
    server = JsonRpcServer("test", "intent")
    # The probe is classified like the handler: a peer-taking handler is a
    # "caller" method, any other only reads.
    kind = caller if getattr(handler, "wants_peer", False) else read
    server.register("probe", kind(handler))
    return server


def test_server_passes_the_kernels_peer_and_drops_a_forged_one():
    seen = {}

    def handler(params):
        seen.update(params)
        return {}

    handler.wants_peer = True
    server = _server_with(handler)
    forged = {"jsonrpc": "2.0", "id": 1, "method": "probe", "params": {"_peer": {"uid": 0}}}
    server.handle_line(json.dumps(forged), Peer(HUMAN))
    assert isinstance(seen["_peer"], Peer) and seen["_peer"].uid == HUMAN.uid


def test_server_never_passes_peer_to_handlers_that_did_not_ask():
    seen = {}

    def handler(params):
        seen.update(params)
        return {}

    server = _server_with(handler)
    server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "probe",
                                   "params": {"_peer": {"uid": 0}, "x": 1}}), Peer(HUMAN))
    assert seen == {"x": 1}


def test_peer_over_a_real_socket_is_the_connecting_process():
    import os

    seen = {}

    def handler(params):
        seen["uid"] = params["_peer"].uid
        seen["pid"] = params["_peer"].pid
        return {}

    handler.wants_peer = True
    server = _server_with(handler)
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    thread = threading.Thread(target=server._serve_client, args=(a,), daemon=True)
    thread.start()
    b.sendall(b'{"jsonrpc":"2.0","id":1,"method":"probe","params":{"_peer":{"uid":0}}}\n')
    b.makefile().readline()
    b.close()
    thread.join(timeout=5)
    assert seen == {"uid": os.getuid(), "pid": os.getpid()}


# --- sessions --------------------------------------------------------------------------


def test_naming_an_actor_never_yields_a_gate_session(tmp_path, monkeypatch):
    """dashboard.get / identity.session create sessions for any actor id the
    client names; the gate must never accept them."""
    monkeypatch.setenv("EIRA_DB_PATH", str(tmp_path / "app.db"))
    from app import session_store

    session_store.init_db()
    sid = session_store.ensure_session(None, "anne@kommune.dk")
    session = session_store.get_session(sid)
    assert session["actor_id"] == "anne@kommune.dk"
    assert not session.get("authenticated_at") and session.get("os_uid") is None


def test_login_binds_the_session_and_never_adopts_an_existing_one(tmp_path, monkeypatch):
    monkeypatch.setenv("EIRA_DB_PATH", str(tmp_path / "app.db"))
    from app import session_store

    session_store.init_db()
    planted = session_store.ensure_session("planted-id", "mallory")
    sid = session_store.create_session_from_claims({"email": "anne@kommune.dk"}, session_id=planted,
                                                   os_uid=HUMAN.uid)
    assert sid != planted
    session = session_store.get_session(sid)
    assert session["os_uid"] == HUMAN.uid and session["authenticated_at"]
    assert not session_store.get_session(planted).get("authenticated_at")


def test_model_attempt_to_decide_is_audited_with_its_own_code(world):
    """Audit/SIEM/Fleet can alert on exactly this event."""
    with acting_as(MODEL):
        world.gate.confirm("dlg-x", "sha256:" + "0" * 64, "sha256:" + "0" * 64, "s-anne")
    with world.store._connect() as conn:
        entry = json.loads(conn.execute("SELECT entry FROM gate_audit ORDER BY seq DESC LIMIT 1").fetchone()["entry"])
    assert entry["error"] == "E_MODEL_CANNOT_DECIDE"
    assert entry["caller"] == {"uid": MODEL.uid, "pid": MODEL.pid, "model": True}


def test_model_cannot_use_a_session_bound_to_itself(world):
    world.sessions["s-anne"]["os_uid"] = MODEL.uid
    with acting_as(MODEL):
        result = world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL)
    assert_no_actor(result, world)


def test_concurrent_insert_cannot_be_adopted_by_a_login(tmp_path, monkeypatch):
    """The fixation window between "is the id free?" and "use it": a row that
    appears in between is never adopted."""
    monkeypatch.setenv("EIRA_DB_PATH", str(tmp_path / "app.db"))
    from app import session_store

    session_store.init_db()
    real_connection = session_store.get_connection

    def racing_connection():
        conn = real_connection()
        conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id, actor_id) VALUES ('wanted-id', 'mallory')"
        )
        return conn

    monkeypatch.setattr(session_store, "get_connection", racing_connection)
    sid = session_store.create_session_from_claims({"email": "anne@kommune.dk"}, session_id="wanted-id",
                                                   os_uid=HUMAN.uid)
    monkeypatch.setattr(session_store, "get_connection", real_connection)
    assert sid != "wanted-id"
    assert session_store.get_session("wanted-id")["actor_id"] == "mallory"
    assert not session_store.get_session("wanted-id").get("authenticated_at")


# --- the model identity must exist where it matters (review of #150) ----------------


def test_installed_gate_refuses_to_start_without_the_model_user(monkeypatch):
    from app.gate import ipc

    monkeypatch.setattr(caller_module, "model_uid", lambda: None)
    monkeypatch.setattr(ipc, "installed", lambda: True)
    monkeypatch.setattr(ipc, "_GATE", None)
    with pytest.raises(caller_module.ModelIdentityMissing, match="does not exist"):
        ipc.default_gate()


@pytest.mark.parametrize("uid, message", [(1000, "not a system uid"), (None, "does not exist")])
def test_model_uid_must_be_a_separate_system_user(monkeypatch, uid, message):
    monkeypatch.setattr(caller_module, "model_uid", lambda: uid)
    with pytest.raises(caller_module.ModelIdentityMissing, match=message):
        caller_module.require_model_identity()


def test_model_uid_cannot_be_the_daemons_uid(monkeypatch):
    import pwd as pwd_module

    monkeypatch.setattr(caller_module, "model_uid", lambda: 991)
    monkeypatch.setattr(caller_module.pwd, "getpwnam",
                        lambda name: pwd_module.struct_passwd(("eira", "x", 991, 991, "", "/", "/bin/false")))
    with pytest.raises(caller_module.ModelIdentityMissing, match="daemons' uid"):
        caller_module.require_model_identity()


def test_any_model_service_runs_as_the_model_user():
    """When a model service is packaged, it must run as eira-model, or the
    gate would not recognise it (and would treat it as a human)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    units = [p for p in [*root.glob("systemd/*.service"), *root.glob("packaging/**/*.service")]
             if "model" in p.name or "ai" in p.stem.split("-")]
    for unit in units:
        assert "User=eira-model" in unit.read_text(), unit
