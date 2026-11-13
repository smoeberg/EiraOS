"""Desktop login on an installed system (GATE-KERNEL bilag A pkt. 1, punkt 2).

identityd creates the only sessions the gate accepts: from verified Entra
claims, bound to the OS user proven by loginuid *and* SO_PEERCRED. Entra is
not called: token exchange and verification are replaced at the seam."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.auth import login, oidc
from app.gate import Decision
from app.gate.caller import acting_as
from app.gate.executors import default_registry
from app.gate.kernel import Gate
from app.gate.policy import Origin
from app.gate.store import GateStore
from app.ipc.jsonrpc import JsonRpcError
from tests.callers import HUMAN, OTHER_HUMAN, Peer
from tests.rights_helpers import TestFleet
from tests.test_gate_kernel import Clock, envelope, raw

OID = "7a9c1e4b-0000-4000-8000-000000000001"
IDENTITY = f"did:eira:entra.{OID}"


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    path = tmp_path / "app.db"
    monkeypatch.setenv("EIRA_DB_PATH", str(path))
    monkeypatch.setenv("EIRA_APP_DB", str(path))
    from app import database, session_store

    monkeypatch.setattr(database, "DB_PATH", path)
    monkeypatch.setenv("EIRA_OIDC_MOCK", "0")
    monkeypatch.setenv("EIRA_ENV", "production")
    monkeypatch.setenv("OIDC_CLIENT_ID", "eira-desktop")
    # Entra as configuration (config.example.env); endpoints overridden so
    # the test makes no discovery request.
    monkeypatch.setenv("OIDC_PROVIDER_ID", "entra")
    monkeypatch.setenv("OIDC_ISSUER", "https://login.microsoftonline.com/kk-tenant/v2.0")
    monkeypatch.setenv(
        "OIDC_AUTHORIZATION_ENDPOINT", "https://login.microsoftonline.com/kk-tenant/oauth2/v2.0/authorize"
    )
    monkeypatch.setenv("OIDC_TOKEN_ENDPOINT", "https://login.microsoftonline.com/kk-tenant/oauth2/v2.0/token")
    monkeypatch.setenv("OIDC_JWKS_URI", "https://login.microsoftonline.com/kk-tenant/discovery/v2.0/keys")
    monkeypatch.delenv("OIDC_TENANT_ID", raising=False)
    database.init_db()
    session_store.init_db()
    return path


@pytest.fixture
def entra(monkeypatch):
    """Entra at the seam: the code exchange returns a token, verification
    returns these claims only for the nonce the login was started with."""
    seen = {}

    def exchange(code, verifier, cfg=None, redirect_uri=None):
        seen["code"], seen["verifier"], seen["redirect_uri"] = code, verifier, redirect_uri
        return {"id_token": "token-for-" + code}

    def claims(id_token, cfg=None, nonce=None):
        seen["nonce"] = nonce
        if not nonce:
            raise ValueError("nonce required")
        return {"email": "anne@kommune.dk", "name": "Anne", "identity": IDENTITY,
                "groups": ["laerere"], "tenant_id": "kk-tenant", "idp": "entra",
                "assurance_level": "idp_authenticated", "sub": "anne"}

    monkeypatch.setattr(oidc, "exchange_code_for_tokens", exchange)
    monkeypatch.setattr(oidc, "claims_from_id_token", claims)
    return seen


@pytest.fixture
def loginuids(monkeypatch):
    table = {HUMAN.pid: HUMAN.uid, OTHER_HUMAN.pid: OTHER_HUMAN.uid}
    monkeypatch.setattr(login, "login_uid", lambda pid, proc=None: table.get(pid))
    return table


REDIRECT = "http://127.0.0.1:49152/callback"


def call(method, caller, **params):
    if method is login.login_start:
        params.setdefault("redirect_uri", REDIRECT)
    return method({**params, "_peer": Peer(caller) if caller else None})


def test_login_creates_a_bound_expiring_session_with_identity_from_claims(app_db, entra, loginuids):
    start = call(login.login_start, HUMAN)
    assert start["authorize_url"].startswith("https://login.microsoftonline.com/kk-tenant/")
    assert "code_challenge=" in start["authorize_url"] and "nonce=" in start["authorize_url"]
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A49152%2Fcallback" in start["authorize_url"]
    done = call(login.login_complete, HUMAN, state=start["state"], code="abc")
    assert done["identity"] == IDENTITY and entra["nonce"]
    assert entra["redirect_uri"] == REDIRECT  # the exchange reuses the authorize redirect
    from app.session_store import get_session

    session = get_session(done["session_id"])
    assert (session["os_uid"], session["identity"], session["groups"]) == (HUMAN.uid, IDENTITY, ["laerere"])
    expires = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
    assert timedelta(hours=11) < expires - datetime.now(timezone.utc) <= timedelta(hours=12)


def test_another_user_cannot_complete_or_consume_the_login(app_db, entra, loginuids):
    start = call(login.login_start, HUMAN)
    with pytest.raises(JsonRpcError, match="invalid_or_expired_state"):
        call(login.login_complete, OTHER_HUMAN, state=start["state"], code="abc")
    assert call(login.login_complete, HUMAN, state=start["state"], code="abc")["identity"] == IDENTITY


def test_a_login_state_is_used_once(app_db, entra, loginuids):
    start = call(login.login_start, HUMAN)
    call(login.login_complete, HUMAN, state=start["state"], code="abc")
    with pytest.raises(JsonRpcError, match="invalid_or_expired_state"):
        call(login.login_complete, HUMAN, state=start["state"], code="abc")


@pytest.mark.parametrize(
    "table, reason",
    [
        ({}, "caller_not_in_a_login_session"),              # loginuid unset (no login session)
        ({HUMAN.pid: 0}, "loginuid_does_not_match_peer"),  # a root-owned login session on the socket
    ],
)
def test_peer_and_loginuid_must_agree(app_db, entra, monkeypatch, table, reason):
    monkeypatch.setattr(login, "login_uid", lambda pid, proc=None: table.get(pid))
    with pytest.raises(JsonRpcError, match=reason):
        call(login.login_start, HUMAN)


def test_no_peer_no_login(app_db, entra):
    with pytest.raises(JsonRpcError, match="login_requires_socket_peer"):
        login.login_start({})


def test_system_users_do_not_log_in(app_db, entra, monkeypatch):
    from tests.callers import MODEL

    monkeypatch.setattr(login, "login_uid", lambda pid, proc=None: MODEL.uid)
    with pytest.raises(JsonRpcError, match="system_users_do_not_log_in"):
        call(login.login_start, MODEL)


def test_login_uid_reads_the_kernel_value(tmp_path):
    (tmp_path / "77").mkdir()
    (tmp_path / "77" / "loginuid").write_text("1000")
    (tmp_path / "78").mkdir()
    (tmp_path / "78" / "loginuid").write_text(str(login.UNSET_LOGINUID))
    assert login.login_uid(77, tmp_path) == 1000
    assert login.login_uid(78, tmp_path) is None
    assert login.login_uid(79, tmp_path) is None


# --- end to end: login → gate ------------------------------------------------------


def test_installed_login_session_is_accepted_by_the_gate(app_db, entra, loginuids, tmp_path):
    """The whole of punkt 2: a desktop login yields a session the gate
    accepts, with the identity and groups from claims — no gate_identities."""

    from app.gate import consent_proof

    start = call(login.login_start, HUMAN)
    done = call(login.login_complete, HUMAN, state=start["state"], code="abc")
    sid, key = done["session_id"], done["consent_key"]  # the key stays in the app's Rust core
    store = GateStore(str(tmp_path / "gate.db"))
    conversation = "obj:sag:42"
    store.add_member(conversation, IDENTITY)
    clock = Clock()
    clock.now = datetime.now(timezone.utc)
    fleet = TestFleet(tmp_path / "rights", clock)
    fleet.grant(conversation, group="laerere").publish()
    from app.session_store import get_session_for_gate

    gate = Gate(store, default_registry(str(tmp_path / "gate.db")), sessions=get_session_for_gate,
                clock=clock, rights=fleet.cache)
    env = envelope()
    env["participants"][0]["identity"] = IDENTITY
    with acting_as(HUMAN):
        proposal = gate.propose(raw(env), sid, Origin.USER)
        assert proposal.code.value == "E_NEED_CONSENT", proposal
        rendering = store.find(env["id"])["rendering_hash"]

        def prove(verb):
            return consent_proof.compute(key, verb, HUMAN.uid, sid, env["id"], proposal.content_hash, rendering)

        # Without the app's proof (another program as the same user): refused.
        refused = gate.grant_consent(env["id"], proposal.content_hash, rendering, sid)
        assert refused.code.value == "E_CONSENT_PROOF"
        gate.grant_consent(env["id"], proposal.content_hash, rendering, sid, prove("consent"))
        result = gate.confirm(env["id"], proposal.content_hash, rendering, sid, prove("confirm"))
    assert result.decision is Decision.PASS
    with acting_as(OTHER_HUMAN):
        assert gate.status(env["id"], sid) is None


def test_consent_key_never_reaches_clients(app_db, entra, loginuids):
    """identity.session and dashboard.get hand sessions to whoever names the
    id; the key must not be among what they see."""
    from app.daemons.identityd import identity_session
    from app.session_store import get_session

    start = call(login.login_start, HUMAN)
    done = call(login.login_complete, HUMAN, state=start["state"], code="abc")
    assert len(done["consent_key"]) == 64
    assert "consent_key" not in get_session(done["session_id"])
    assert "consent_key" not in identity_session({"session_id": done["session_id"]})


def test_on_an_installed_system_the_app_never_gets_the_key(app_db, entra, loginuids, monkeypatch):
    """EIRA-CONSENT-AGENT §5.3: only the registered consent agent claims it."""
    monkeypatch.setattr("app.gate.caller.installed", lambda: True)
    start = call(login.login_start, HUMAN)
    done = call(login.login_complete, HUMAN, state=start["state"], code="abc")
    assert "consent_key" not in done and done["session_id"]


def test_expired_session_is_no_session(app_db, entra, loginuids, tmp_path):
    from app.session_store import get_connection, get_session

    start = call(login.login_start, HUMAN)
    sid = call(login.login_complete, HUMAN, state=start["state"], code="abc")["session_id"]
    with get_connection() as conn:
        conn.execute("UPDATE sessions SET expires_at = '2020-01-01T00:00:00Z' WHERE session_id = ?", (sid,))
        conn.commit()
    gate = Gate(GateStore(str(tmp_path / "g.db")), default_registry(str(tmp_path / "g.db")),
                sessions=get_session, rights=TestFleet(tmp_path / "r", Clock()).cache)
    with acting_as(HUMAN):
        assert gate._actor(sid) is None


def test_session_without_expiry_is_no_session(app_db, entra, loginuids, tmp_path):
    """Fail closed: a pre-upgrade row without expires_at never counts."""
    from app.session_store import get_connection, get_session, session_of_caller

    start = call(login.login_start, HUMAN)
    sid = call(login.login_complete, HUMAN, state=start["state"], code="abc")["session_id"]
    with get_connection() as conn:
        conn.execute("UPDATE sessions SET expires_at = NULL WHERE session_id = ?", (sid,))
        conn.commit()
    assert session_of_caller(HUMAN.uid, sid) is None
    gate = Gate(GateStore(str(tmp_path / "g.db")), default_registry(str(tmp_path / "g.db")),
                sessions=get_session, rights=TestFleet(tmp_path / "r", Clock()).cache)
    with acting_as(HUMAN):
        assert gate._actor(sid) is None


def test_identityd_registers_login_with_the_peer(app_db):
    from app.daemons.identityd import register_identity_handlers

    class Server:
        def __init__(self):
            self.methods = {}

        def register(self, name, handler):
            self.methods[name] = handler

    server = Server()
    register_identity_handlers(server)
    for name in ("identity.login_start", "identity.login_complete"):
        assert getattr(server.methods[name], "wants_peer", False), name
    assert json.dumps(sorted(server.methods))  # registered without error


@pytest.mark.parametrize(
    "redirect",
    [
        "http://localhost:49152/callback",          # a name can resolve elsewhere
        "http://127.0.0.1/callback",                # no explicit port
        "http://127.0.0.1:80/callback",             # privileged port
        "http://127.0.0.1:49152/other",             # another path
        "https://evil.example/callback",
        "http://127.0.0.1:49152/callback?x=1",
        "http://127.0.0.1:99999/callback",
    ],
)
def test_only_the_ipv4_loopback_callback_is_accepted(app_db, loginuids, redirect):
    with pytest.raises(JsonRpcError, match="redirect_uri"):
        call(login.login_start, HUMAN, redirect_uri=redirect)


def test_redirect_is_required(app_db, loginuids):
    with pytest.raises(JsonRpcError, match="redirect_uri is required"):
        login.login_start({"_peer": Peer(HUMAN)})


def test_login_fails_closed_when_the_provider_moves_to_another_issuer(app_db, entra, loginuids, monkeypatch):
    """EIRA-IDENTITY 1.0 §3: rights sets name did:eira:entra.<oid>. Pointing
    "entra" at another issuer must not hand that issuer those identities."""
    start = call(login.login_start, HUMAN)
    call(login.login_complete, HUMAN, state=start["state"], code="abc")
    monkeypatch.setenv("OIDC_ISSUER", "https://idp.attacker.example/v2.0")
    start = call(login.login_start, HUMAN)
    with pytest.raises(JsonRpcError) as err:
        call(login.login_complete, HUMAN, state=start["state"], code="def")
    assert "provider_issuer_changed" in str(err.value.data)
