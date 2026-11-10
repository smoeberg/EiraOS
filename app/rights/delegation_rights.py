from __future__ import annotations
from app.auth.delegation import DelegationCheckRequest,DelegationService
class DelegationAwareRightsAgent:
    def __init__(self,rights_agent):self.rights_agent=rights_agent;self.delegations=DelegationService()
    def can_act(self,actor,action,target):
        if self.rights_agent.can_act(actor,action,target):return True
        return action=="prepare" and self.delegations.check_delegation(DelegationCheckRequest(delegee_id=actor,action=action,target=target))
