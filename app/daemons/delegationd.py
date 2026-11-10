"""Delegation Daemon - Manages delegation tokens for "På vegne af" protocol.

This daemon provides IPC endpoints for creating, validating, and revoking
delegation tokens that allow models to prepare actions on behalf of users.

Security:
- All delegation tokens are cryptographically signed
- Tokens have short expiration (max 1 hour)
- All operations are logged to stated daemon
- Delegation is revocable at any time

Architecture:
- Runs as user:group = eira:eira
- Unix socket: /run/eira/delegationd.sock
- AppArmor: usr.bin.eira-delegationd
- systemd: eira-delegationd.service
"""

from __future__ import annotations

import logging
from typing import Any

from app.daemons.base import JsonRpcServer
from app.gate.delegation import (
    DELEGATABLE_ACTIONS,
    SCOPE_LEVELS,
    create_delegation_token,
    list_delegation_tokens,
    revoke_delegation_token,
    verify_delegation_token,
)
from app.ipc.jsonrpc import (
    INVALID_PARAMS,
    JsonRpcError,
)

logger = logging.getLogger(__name__)


def register_delegation_handlers(server: JsonRpcServer) -> None:
    """Register delegation handlers with a JSON-RPC server."""
    
    def delegation_create(params: dict[str, Any]) -> dict[str, Any]:
        """Create a new delegation token.
        
        Required params:
            delegator_id: Who is delegating (user ID)
            delegatee_id: Who is being delegated to (model/service ID)
            action_type: What action can be delegated
        
        Optional params:
            scope: Level of access (read, write, admin) - default: read
            resource_pattern: Pattern for allowed resources
            ttl_seconds: Time-to-live in seconds (max 3600)
            delegator_name: Human-readable name for delegator
            metadata: Additional metadata
        
        Returns:
            signed_token: The signed delegation token
            token_id: The token identifier
            expires_at: When the token expires
        """
        # Validate required params
        delegator_id = params.get("delegator_id")
        delegatee_id = params.get("delegatee_id")
        action_type = params.get("action_type")
        
        if not delegator_id or not isinstance(delegator_id, str):
            raise JsonRpcError(
                INVALID_PARAMS,
                "delegator_id is required",
                {"user_message": "Delegator ID skal angives"}
            )
        
        if not delegatee_id or not isinstance(delegatee_id, str):
            raise JsonRpcError(
                INVALID_PARAMS,
                "delegatee_id is required",
                {"user_message": "Delegatee ID skal angives"}
            )
        
        if not action_type or not isinstance(action_type, str):
            raise JsonRpcError(
                INVALID_PARAMS,
                "action_type is required",
                {"user_message": "Action type skal angives"}
            )
        
        if action_type not in DELEGATABLE_ACTIONS:
            raise JsonRpcError(
                INVALID_PARAMS,
                f"action_type must be one of {DELEGATABLE_ACTIONS}",
                {"user_message": f"Action type skal være en af {DELEGATABLE_ACTIONS}"}
            )
        
        # Get optional params
        scope = params.get("scope", "read")
        if scope not in SCOPE_LEVELS:
            raise JsonRpcError(
                INVALID_PARAMS,
                f"scope must be one of {SCOPE_LEVELS}",
                {"user_message": f"Scope skal være en af {SCOPE_LEVELS}"}
            )
        
        resource_pattern = params.get("resource_pattern")
        ttl_seconds = params.get("ttl_seconds")
        delegator_name = params.get("delegator_name")
        metadata = params.get("metadata", {})
        
        # Convert ttl_seconds to timedelta
        from datetime import timedelta
        ttl = timedelta(seconds=ttl_seconds) if ttl_seconds else None
        
        # Create token
        signed_token = create_delegation_token(
            delegator_id=delegator_id,
            delegatee_id=delegatee_id,
            action_type=action_type,
            scope=scope,
            resource_pattern=resource_pattern,
            ttl=ttl,
            delegator_name=delegator_name,
            metadata=metadata,
        )
        
        # Split token to get token_id
        token_id = signed_token.split(":")[0]
        
        # Log the delegation
        _log_delegation_event(
            action="delegation.create",
            delegator_id=delegator_id,
            delegatee_id=delegatee_id,
            action_type=action_type,
            scope=scope,
            token_id=token_id,
            result="success"
        )
        
        return {
            "signed_token": signed_token,
            "token_id": token_id,
            "expires_at": _get_expiration_time(ttl_seconds).isoformat() if ttl_seconds else None
        }
    
    def delegation_verify(params: dict[str, Any]) -> dict[str, Any]:
        """Verify a delegation token for a specific action.
        
        Required params:
            delegation_token: The signed delegation token
            action: The action being attempted
        
        Optional params:
            resource: The resource being accessed
        
        Returns:
            valid: Whether the token is valid
            delegator_id: Who delegated (if valid)
            delegatee_id: Who was delegated to (if valid)
            action_type: What action is allowed (if valid)
            scope: Level of access (if valid)
        """
        delegation_token = params.get("delegation_token")
        action = params.get("action")
        resource = params.get("resource")
        
        if not delegation_token or not isinstance(delegation_token, str):
            raise JsonRpcError(
                INVALID_PARAMS,
                "delegation_token is required",
                {"user_message": "Delegationstoken skal angives"}
            )
        
        if not action or not isinstance(action, str):
            raise JsonRpcError(
                INVALID_PARAMS,
                "action is required",
                {"user_message": "Action skal angives"}
            )
        
        # Verify token
        token = verify_delegation_token(delegation_token, action, resource)
        
        if token is None:
            _log_delegation_event(
                action="delegation.verify",
                delegation_token=delegation_token[:20] + "...",
                action=action,
                result="invalid"
            )
            return {
                "valid": False,
                "error": "Invalid or expired token"
            }
        
        # Log successful verification
        _log_delegation_event(
            action="delegation.verify",
            delegator_id=token.delegator_id,
            delegatee_id=token.delegatee_id,
            action_type=token.action_type,
            token_id=token.token_id,
            result="success"
        )
        
        return {
            "valid": True,
            "delegator_id": token.delegator_id,
            "delegator_name": token.delegator_name,
            "delegatee_id": token.delegatee_id,
            "delegatee_type": token.delegatee_type,
            "action_type": token.action_type,
            "scope": token.scope,
            "resource_pattern": token.resource_pattern,
            "created_at": token.created_at.isoformat(),
            "expires_at": token.expires_at.isoformat(),
            "token_id": token.token_id,
        }
    
    def delegation_revoke(params: dict[str, Any]) -> dict[str, Any]:
        """Revoke a delegation token.
        
        Required params:
            token_id: The token identifier to revoke
        
        Returns:
            success: Whether the revocation was successful
        """
        token_id = params.get("token_id")
        
        if not token_id or not isinstance(token_id, str):
            raise JsonRpcError(
                INVALID_PARAMS,
                "token_id is required",
                {"user_message": "Token ID skal angives"}
            )
        
        # Revoke token
        success = revoke_delegation_token(token_id)
        
        if success:
            _log_delegation_event(
                action="delegation.revoke",
                token_id=token_id,
                result="success"
            )
        else:
            _log_delegation_event(
                action="delegation.revoke",
                token_id=token_id,
                result="not_found"
            )
        
        return {"success": success}
    
    def delegation_list(params: dict[str, Any]) -> dict[str, Any]:
        """List all active delegation tokens.
        
        Optional params:
            delegator_id: Filter by delegator ID
        
        Returns:
            tokens: List of delegation tokens
        """
        delegator_id = params.get("delegator_id")
        tokens = list_delegation_tokens(delegator_id)
        
        _log_delegation_event(
            action="delegation.list",
            delegator_id=delegator_id,
            count=len(tokens),
            result="success"
        )
        
        return {"tokens": tokens}
    
    def delegation_health(params: dict[str, Any]) -> dict[str, Any]:
        """Health check for delegation service."""
        return {
            "daemon": "eira-delegationd",
            "status": "healthy",
            "version": "1.0",
            "delegatable_actions": list(DELEGATABLE_ACTIONS),
            "scope_levels": list(SCOPE_LEVELS),
        }
    
    # Register handlers
    server.register("delegation.create", delegation_create)
    server.register("delegation.verify", delegation_verify)
    server.register("delegation.revoke", delegation_revoke)
    server.register("delegation.list", delegation_list)
    server.register("health", delegation_health)


def _log_delegation_event(**kwargs) -> None:
    """Log a delegation event to the stated daemon."""
    try:
        from app.ipc.client import IpcClient
        client = IpcClient("stated", timeout=2.0)
        client.call("audit.append", {
            "event_type": "delegation",
            "details": kwargs
        })
    except Exception as exc:
        logger.warning(f"Failed to log delegation event: {exc}")


def _get_expiration_time(ttl_seconds: int | None) -> Any:
    """Get expiration time from TTL seconds."""
    from datetime import datetime, timedelta, timezone
    if ttl_seconds is None:
        return datetime.now(timezone.utc) + timedelta(minutes=30)
    return datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
