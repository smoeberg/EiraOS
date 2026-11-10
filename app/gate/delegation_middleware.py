from __future__ import annotations
from functools import wraps
from app.auth.delegation import DelegationCheckRequest,DelegationService
from app.gate.caller import current
_SERVICE=DelegationService()
def with_delegation_check(action=None,target=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args,**kwargs):
            caller=current()
            if caller is None:raise PermissionError("no caller context")
            if caller.acting_as is None:return func(*args,**kwargs)
            if not action or not target:raise PermissionError("delegation scope is incomplete")
            if not _SERVICE.check_delegation(DelegationCheckRequest(delegee_id=caller.acting_as,action=action,target=target)):
                raise PermissionError("delegation denied")
            return func(*args,**kwargs)
        return wrapper
    return decorator
def requires_delegation(action,target):return with_delegation_check(action,target)
