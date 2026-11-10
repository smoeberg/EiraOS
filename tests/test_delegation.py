from datetime import timedelta
from unittest.mock import patch
import pytest
from app.auth.delegation import DelegationCreateRequest,DelegationScope,DelegationService,DelegationCheckRequest,DelegationRevokeRequest

def request(actions=("prepare",),targets=("*",),expires=timedelta(hours=1)):
    return DelegationCreateRequest(delegee_id="model:eira-model",scope=DelegationScope(actions=list(actions),targets=list(targets)),expires_in=expires)

def test_execute_and_decide_are_never_delegable():
    service=DelegationService()
    with pytest.raises(PermissionError): service.create_delegation("user:alice",request(("execute",)))
    with pytest.raises(PermissionError): service.create_delegation("user:alice",request(("decide",)))

def test_delegation_expires_and_revokes():
    service=DelegationService()
    d=service.create_delegation("user:alice",request())
    assert service.check_delegation(DelegationCheckRequest("model:eira-model","prepare","intent:create"))
    assert service.revoke_delegation(DelegationRevokeRequest(delegation_id=d.id),"user:alice")
    assert not service.check_delegation(DelegationCheckRequest("model:eira-model","prepare","intent:create"))

def test_delegation_audit_failure_rolls_back_creation():
    service=DelegationService()
    with patch.object(service,"_audit",side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError):
            service.create_delegation("user:alice",request())
    assert service.repo.active_for_delegator("user:alice")==[]


def test_target_wildcard_matches_intent_namespace():
    service=DelegationService()
    service.create_delegation("user:alice", request(targets=("intent:*",)))
    assert service.check_delegation(DelegationCheckRequest("model:eira-model","prepare","intent:utterance"))
    assert not service.check_delegation(DelegationCheckRequest("model:eira-model","prepare","state:update"))
