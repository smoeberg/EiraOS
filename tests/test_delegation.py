"""EIRA-DELEGATION-1.0: the model may only prepare, only for the human who
delegated, and a delegation is created only through the trusted path."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest

from app.auth.delegation import (
    DelegationCheckRequest,
    DelegationCreateRequest,
    DelegationRepository,
    DelegationRevokeRequest,
    DelegationScope,
    DelegationService,
)
from app.daemons.delegationd import BAD_PROOF, NOT_ALLOWED, register_delegation_handlers
from app.gate import consent_proof
from app.ipc.jsonrpc import JsonRpcError
from tests.callers import HUMAN, MODEL, OTHER_HUMAN, Peer

MODEL_ID = "model:eira-model"


def request(actions=("prepare",), targets=("*",), expires=timedelta(hours=1)):
    return DelegationCreateRequest(
        delegee_id=MODEL_ID,
        scope=DelegationScope(actions=list(actions), targets=list(targets)),
        expires_in=expires,
    )


def check(service, target="intent:create", delegee=MODEL_ID):
    return service.check_delegation(DelegationCheckRequest(delegee_id=delegee, action="prepare", target=target))


@pytest.fixture
def service(tmp_path):
    """Its own database: nothing leaks between tests or into data/."""
    svc = DelegationService(DelegationRepository(tmp_path / "app.db"))
    with patch.object(svc, "_audit"):
        yield svc


# --- what can be delegated ----------------------------------------------------------


@pytest.mark.parametrize("action", ["execute", "decide", "admin", "consent", "confirm", "*"])
def test_only_prepare_can_be_delegated(service, action):
    with pytest.raises(PermissionError):
        service.create_delegation("user:alice", request((action,)))
    with pytest.raises(PermissionError):
        service.propose_delegation("user:alice", "s-1", request((action,)))


def test_delegation_expires_and_revokes(service):
    delegation = service.create_delegation("user:alice", request())
    assert check(service)
    assert service.revoke_delegation(DelegationRevokeRequest(delegation_id=delegation.id), "user:alice")
    assert not check(service)


def test_only_the_delegator_can_revoke(service):
    delegation = service.create_delegation("user:alice", request())
    with pytest.raises(PermissionError):
        service.revoke_delegation(DelegationRevokeRequest(delegation_id=delegation.id), "user:bob")


def test_delegation_audit_failure_rolls_back_creation(tmp_path):
    svc = DelegationService(DelegationRepository(tmp_path / "app.db"))
    with patch.object(svc, "_audit", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError):
            svc.create_delegation("user:alice", request())
    assert svc.repo.active_for_delegator("user:alice") == []


def test_target_wildcard_matches_intent_namespace(service):
    service.create_delegation("user:alice", request(targets=("intent:*",)))
    assert check(service, "intent:utterance")
    assert not check(service, "state:update")


def test_another_human_s_delegation_never_counts(service):
    service.create_delegation("user:bob", request())
    assert service.delegation_for(MODEL_ID, "prepare", "intent:create", delegator="user:alice") is None
    assert service.delegation_for(MODEL_ID, "prepare", "intent:create", delegator="user:bob") is not None


# --- the trusted path ---------------------------------------------------------------


def test_a_proposal_fixes_the_text_the_user_approves(service):
    proposal = service.propose_delegation("user:alice", "s-1", request(targets=("intent:utterance",)))
    text = proposal["rendering"]["text"]
    assert MODEL_ID in text and "intent:utterance" in text and "samtykke" in text
    assert proposal["rendering"]["hash"].startswith("sha256:")
    assert not check(service, "intent:utterance")  # nothing is active yet


def test_activation_is_single_use_and_bound_to_what_was_shown(service):
    p = service.propose_delegation("user:alice", "s-1", request())
    args = ("user:alice", "s-1", p["proposal_id"], p["content_hash"], p["rendering"]["hash"])
    for wrong in (
        ("user:bob", *args[1:]),
        (args[0], "s-2", *args[2:]),
        (*args[:3], "sha256:" + "0" * 64, args[4]),
        (*args[:4], "sha256:" + "0" * 64),
    ):
        with pytest.raises(PermissionError):
            service.activate(*wrong)
    service.activate(*args)
    assert check(service)
    with pytest.raises(PermissionError):
        service.activate(*args)  # replay


def test_a_stale_proposal_cannot_be_activated(service, monkeypatch):
    import app.auth.delegation as module

    p = service.propose_delegation("user:alice", "s-1", request())
    monkeypatch.setattr(module, "PROPOSAL_TTL", timedelta(seconds=-1))
    with pytest.raises(PermissionError):
        service.activate("user:alice", "s-1", p["proposal_id"], p["content_hash"], p["rendering"]["hash"])


# --- over the socket ----------------------------------------------------------------


KEY = "2" * 64
SESSIONS = {
    "s-anne": {"identity": "did:eira:anne", "authenticated_at": "x", "os_uid": HUMAN.uid, "consent_key": KEY},
}


class FakeServer:
    def __init__(self):
        self.methods = {}

    def register(self, method, handler):
        self.methods[method] = handler


@pytest.fixture
def daemon(service, monkeypatch):
    import app.session_store as store

    monkeypatch.setattr(store, "get_session_for_gate", lambda sid: SESSIONS.get(sid))
    server = FakeServer()
    register_delegation_handlers(server, service)

    def call(method, params, as_=HUMAN):
        handler = server.methods[method]
        assert handler.wants_peer
        return handler({**params, "_peer": Peer(as_)})

    return call


def proposed(daemon):
    return daemon("delegation.propose", {
        "session_id": "s-anne", "delegee_id": MODEL_ID,
        "scope": {"actions": ["prepare"], "targets": ["intent:*"]}, "expires_in": 3600,
    })


def created(daemon, p, proof=None, as_=HUMAN):
    proof = proof or consent_proof.compute(KEY, "delegate", HUMAN.uid, "s-anne", p["proposal_id"],
                                           p["content_hash"], p["rendering"]["hash"])
    return daemon("delegation.create", {
        "session_id": "s-anne", "proposal_id": p["proposal_id"], "content_hash": p["content_hash"],
        "rendering_hash": p["rendering"]["hash"], "proof": proof,
    }, as_)


def test_the_app_can_delegate_with_its_proof(daemon, service):
    result = created(daemon, proposed(daemon))
    assert result["status"] == "created" and result["delegator_id"] == "did:eira:anne"
    assert check(service, "intent:utterance")


def test_without_the_app_s_proof_nobody_can_delegate(daemon, service):
    p = proposed(daemon)
    wrong = (
        None,
        "0" * 64,
        consent_proof.compute(KEY, "consent", HUMAN.uid, "s-anne", p["proposal_id"],
                              p["content_hash"], p["rendering"]["hash"]),  # another verb
        consent_proof.compute("3" * 64, "delegate", HUMAN.uid, "s-anne", p["proposal_id"],
                              p["content_hash"], p["rendering"]["hash"]),  # another key
    )
    for proof in wrong:
        with pytest.raises(JsonRpcError) as error:
            daemon("delegation.create", {
                "session_id": "s-anne", "proposal_id": p["proposal_id"], "content_hash": p["content_hash"],
                "rendering_hash": p["rendering"]["hash"], "proof": proof,
            })
        assert error.value.code == BAD_PROOF
    assert not check(service, "intent:utterance")


def test_the_session_must_be_the_caller_s_and_human(daemon, monkeypatch):
    import app.gate.caller as caller_module

    for who in (OTHER_HUMAN, MODEL):
        if who is MODEL:
            monkeypatch.setattr(caller_module, "model_uid", lambda: MODEL.uid)
        with pytest.raises(JsonRpcError) as error:
            daemon("delegation.propose", {"session_id": "s-anne", "delegee_id": MODEL_ID,
                                          "scope": {"actions": ["prepare"]}}, who)
        assert error.value.code == NOT_ALLOWED


def test_a_model_may_only_check_its_own_delegations(daemon, monkeypatch):
    import app.gate.caller as caller_module

    monkeypatch.setattr(caller_module, "model_uid", lambda: MODEL.uid)
    own = caller_module.model_identity(MODEL)
    assert daemon("delegation.check", {"delegee_id": own, "action": "prepare", "target": "intent:x"},
                  MODEL) == {"valid": False}
    with pytest.raises(JsonRpcError):
        daemon("delegation.check", {"delegee_id": "model:other", "action": "prepare", "target": "x"}, MODEL)


def test_the_command_line_cannot_delegate(capsys):
    from app.cli.delegation import main

    assert main(["create", "--session-id", "s", "--delegee", MODEL_ID,
                 "--scope", '{"actions":["prepare"]}']) == 2
    assert "EiraOS-appen" in capsys.readouterr().err
