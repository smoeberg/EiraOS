"""Delegation Protocol for EiraOS - "På vegne af" (On Behalf Of).

This module implements the delegation protocol that allows the model to prepare
actions for a specific person without being able to decide anything itself.

Security Principles:
- Delegation tokens are cryptographically signed
- Tokens bind to: delegator, delegatee, action type, scope, expiration
- Model can only PREPARE actions, not EXECUTE them
- All delegated actions are traceable in audit log
- Delegation is revocable
- Fail-closed: Unknown/malformed tokens are rejected

Architecture:
- Delegation tokens are HMAC-SHA256 signed
- Tokens have short expiration (max 1 hour)
- Delegation scope is minimal (principle of least privilege)
- All delegation operations are logged to stated
- Delegation store tracks all active delegations
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.ipc.jsonrpc import JsonRpcError

logger = logging.getLogger(__name__)

# Delegation constants
DELEGATION_DOMAIN = b"EIRA-DELEGATION-V1"
DELEGATION_KEY_BYTES = 32
DELEGATION_TOKEN_BYTES = 64  # hex encoded SHA256
MAX_DELEGATION_TTL = timedelta(hours=1)  # Maximum delegation lifetime
DEFAULT_DELEGATION_TTL = timedelta(minutes=30)  # Default delegation lifetime

# Action types that can be delegated
DELEGATABLE_ACTIONS = frozenset({
    "model.prepare",
    "intent.prepare",
    "action.prepare",
    "consent.prepare",
})

# Scope levels
SCOPE_LEVELS = frozenset({
    "read",
    "write",
    "admin",
})


@dataclass(frozen=True)
class DelegationToken:
    """A delegation token that allows a model to act on behalf of a user."""
    
    # Token identifier (UUID)
    token_id: str
    
    # Who is delegating (the user)
    delegator_id: str
    
    # Who is being delegated to (the model/worker)
    delegatee_id: str
    
    # What can be delegated
    action_type: str
    
    # Optional fields with defaults
    delegator_name: str | None = None
    delegatee_type: str = "model"  # model, service, user
    scope: str = "read"
    resource_pattern: str | None = None
    
    # When it's valid
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + DEFAULT_DELEGATION_TTL)
    
    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        """Check if the token has expired."""
        return datetime.now(timezone.utc) > self.expires_at
    
    def is_valid_action(self, action: str) -> bool:
        """Check if the action is allowed by this token."""
        if self.is_expired():
            return False
        return self.action_type == action
    
    def to_dict(self) -> dict[str, Any]:
        """Convert token to dictionary."""
        return {
            "token_id": self.token_id,
            "delegator_id": self.delegator_id,
            "delegator_name": self.delegator_name,
            "delegatee_id": self.delegatee_id,
            "delegatee_type": self.delegatee_type,
            "action_type": self.action_type,
            "scope": self.scope,
            "resource_pattern": self.resource_pattern,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DelegationToken:
        """Create token from dictionary."""
        return cls(
            token_id=data["token_id"],
            delegator_id=data["delegator_id"],
            delegator_name=data.get("delegator_name"),
            delegatee_id=data["delegatee_id"],
            delegatee_type=data.get("delegatee_type", "model"),
            action_type=data["action_type"],
            scope=data.get("scope", "read"),
            resource_pattern=data.get("resource_pattern"),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            metadata=data.get("metadata", {}),
        )


class DelegationError(Exception):
    """Raised when delegation fails."""
    pass


class DelegationStore:
    """Store for managing delegation tokens.
    
    This store keeps track of all active delegation tokens and their status.
    """
    
    def __init__(self):
        self._tokens: dict[str, DelegationToken] = {}
        self._revoked: set[str] = set()
        self._key: str | None = None
    
    def init_key(self, key: str | None = None) -> str:
        """Initialize or get the delegation signing key."""
        if key:
            self._key = key
        elif self._key is None:
            # Generate a new key if none exists
            self._key = secrets.token_hex(DELEGATION_KEY_BYTES)
        return self._key
    
    def create_token(
        self,
        delegator_id: str,
        delegatee_id: str,
        action_type: str,
        scope: str = "read",
        resource_pattern: str | None = None,
        ttl: timedelta | None = None,
        delegator_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DelegationToken:
        """Create a new delegation token.
        
        Args:
            delegator_id: Who is delegating (user ID)
            delegatee_id: Who is being delegated to (model/service ID)
            action_type: What action can be delegated
            scope: Level of access (read, write, admin)
            resource_pattern: Pattern for allowed resources
            ttl: Time-to-live for the token
            delegator_name: Human-readable name for delegator
            metadata: Additional metadata
        
        Returns:
            DelegationToken: The created token
        
        Raises:
            DelegationError: If token creation fails
        """
        # Validate inputs
        if not delegator_id or not isinstance(delegator_id, str):
            raise DelegationError("delegator_id is required")
        
        if not delegatee_id or not isinstance(delegatee_id, str):
            raise DelegationError("delegatee_id is required")
        
        if not action_type or not isinstance(action_type, str):
            raise DelegationError("action_type is required")
        
        if action_type not in DELEGATABLE_ACTIONS:
            raise DelegationError(f"action_type must be one of {DELEGATABLE_ACTIONS}")
        
        if scope not in SCOPE_LEVELS:
            raise DelegationError(f"scope must be one of {SCOPE_LEVELS}")
        
        # Set TTL
        if ttl is None:
            ttl = DEFAULT_DELEGATION_TTL
        elif ttl > MAX_DELEGATION_TTL:
            raise DelegationError(f"TTL cannot exceed {MAX_DELEGATION_TTL}")
        
        # Create token
        token = DelegationToken(
            token_id=secrets.token_hex(16),
            delegator_id=delegator_id,
            delegator_name=delegator_name,
            delegatee_id=delegatee_id,
            action_type=action_type,
            scope=scope,
            resource_pattern=resource_pattern,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + ttl,
            metadata=metadata or {},
        )
        
        # Store token
        self._tokens[token.token_id] = token
        
        logger.info(f"Created delegation token {token.token_id} for {delegator_id} -> {delegatee_id}")
        
        return token
    
    def get_token(self, token_id: str) -> DelegationToken | None:
        """Get a delegation token by ID."""
        token = self._tokens.get(token_id)
        if token and not token.is_expired() and token.token_id not in self._revoked:
            return token
        return None
    
    def validate_token(self, token_id_or_signed: str, action: str, resource: str | None = None) -> bool:
        """Validate a delegation token for a specific action.
        
        Args:
            token_id: The token ID to validate
            action: The action being attempted
            resource: The resource being accessed
        
        Returns:
            bool: True if the token is valid for the action
        """
        # Extract token_id from signed token if needed
        if ":" in token_id_or_signed:
            token_id = token_id_or_signed.split(":", 1)[0]
        else:
            token_id = token_id_or_signed
        
        token = self.get_token(token_id)
        if token is None:
            return False
        
        # Check action
        if not token.is_valid_action(action):
            return False
        
        # Check resource pattern
        if token.resource_pattern and resource:
            # Simple pattern matching (can be enhanced)
            if token.resource_pattern != "*" and token.resource_pattern != resource:
                return False
        
        return True
    
    def revoke_token(self, token_id: str) -> bool:
        """Revoke a delegation token."""
        if token_id in self._tokens:
            self._revoked.add(token_id)
            logger.info(f"Revoked delegation token {token_id}")
            return True
        return False
    
    def revoke_by_delegator(self, delegator_id: str) -> int:
        """Revoke all tokens for a specific delegator."""
        count = 0
        for token_id, token in list(self._tokens.items()):
            if token.delegator_id == delegator_id:
                self._revoked.add(token_id)
                count += 1
        logger.info(f"Revoked {count} tokens for delegator {delegator_id}")
        return count
    
    def revoke_by_delegatee(self, delegatee_id: str) -> int:
        """Revoke all tokens for a specific delegatee."""
        count = 0
        for token_id, token in list(self._tokens.items()):
            if token.delegatee_id == delegatee_id:
                self._revoked.add(token_id)
                count += 1
        logger.info(f"Revoked {count} tokens for delegatee {delegatee_id}")
        return count
    
    def list_tokens(self, delegator_id: str | None = None) -> list[DelegationToken]:
        """List all active delegation tokens."""
        tokens = []
        for token in self._tokens.values():
            if token.is_expired() or token.token_id in self._revoked:
                continue
            if delegator_id is None or token.delegator_id == delegator_id:
                tokens.append(token)
        return tokens
    
    def sign_token(self, token: DelegationToken) -> str:
        """Sign a delegation token.
        
        Args:
            token: The token to sign
        
        Returns:
            str: The signed token string
        """
        if self._key is None:
            raise DelegationError("Signing key not initialized")
        
        # Create message to sign
        message = self._create_signing_message(token)
        
        # Sign with HMAC-SHA256
        signature = hmac.new(
            self._key.encode(),
            message,
            hashlib.sha256
        ).hexdigest()
        
        # Return token_id:signature format
        return f"{token.token_id}:{signature}"
    
    def verify_token(self, signed_token: str) -> DelegationToken | None:
        """Verify a signed delegation token.
        
        Args:
            signed_token: The signed token string (token_id:signature)
        
        Returns:
            DelegationToken: The verified token, or None if invalid
        """
        if self._key is None:
            raise DelegationError("Signing key not initialized")
        
        # Split token and signature
        try:
            token_id, signature = signed_token.split(":", 1)
        except ValueError:
            return None
        
        # Get token from store
        token = self.get_token(token_id)
        if token is None:
            return None
        
        # Verify signature
        message = self._create_signing_message(token)
        expected_signature = hmac.new(
            self._key.encode(),
            message,
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            return None
        
        return token
    
    def _create_signing_message(self, token: DelegationToken) -> bytes:
        """Create the message to sign for a token."""
        parts = [
            DELEGATION_DOMAIN,
            token.token_id.encode(),
            token.delegator_id.encode(),
            token.delegatee_id.encode(),
            token.action_type.encode(),
            token.scope.encode(),
            token.created_at.isoformat().encode(),
            token.expires_at.isoformat().encode(),
        ]
        if token.resource_pattern:
            parts.append(token.resource_pattern.encode())
        return b"\0".join(parts)


# Global delegation store instance
_delegation_store: DelegationStore | None = None


def get_delegation_store() -> DelegationStore:
    """Get or create the global delegation store."""
    global _delegation_store
    if _delegation_store is None:
        _delegation_store = DelegationStore()
        # Initialize key from environment or generate new
        key = os.environ.get("EIRA_DELEGATION_KEY")
        _delegation_store.init_key(key)
    return _delegation_store


def create_delegation_token(
    delegator_id: str,
    delegatee_id: str,
    action_type: str,
    scope: str = "read",
    resource_pattern: str | None = None,
    ttl: timedelta | None = None,
    delegator_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Create and sign a delegation token.
    
    Args:
        delegator_id: Who is delegating
        delegatee_id: Who is being delegated to
        action_type: What action can be delegated
        scope: Level of access
        resource_pattern: Pattern for allowed resources
        ttl: Time-to-live
        delegator_name: Human-readable name for delegator
        metadata: Additional metadata
    
    Returns:
        str: The signed delegation token
    
    Raises:
        DelegationError: If token creation fails
    """
    store = get_delegation_store()
    token = store.create_token(
        delegator_id=delegator_id,
        delegatee_id=delegatee_id,
        action_type=action_type,
        scope=scope,
        resource_pattern=resource_pattern,
        ttl=ttl,
        delegator_name=delegator_name,
        metadata=metadata,
    )
    return store.sign_token(token)


def verify_delegation_token(
    signed_token: str,
    action: str,
    resource: str | None = None,
) -> DelegationToken | None:
    """Verify a delegation token for a specific action.
    
    Args:
        signed_token: The signed token string
        action: The action being attempted
        resource: The resource being accessed
    
    Returns:
        DelegationToken: The verified token, or None if invalid
    """
    store = get_delegation_store()
    token = store.verify_token(signed_token)
    if token is None:
        return None
    if not store.validate_token(signed_token, action, resource):
        return None
    return token


def revoke_delegation_token(token_id: str) -> bool:
    """Revoke a delegation token."""
    store = get_delegation_store()
    return store.revoke_token(token_id)


def list_delegation_tokens(delegator_id: str | None = None) -> list[dict[str, Any]]:
    """List all active delegation tokens."""
    store = get_delegation_store()
    tokens = store.list_tokens(delegator_id)
    return [token.to_dict() for token in tokens]


class DelegationMiddleware:
    """Middleware for validating delegation tokens in handlers."""
    
    def __init__(self, action_type: str):
        self.action_type = action_type
    
    def __call__(self, handler):
        """Decorator to validate delegation tokens."""
        def wrapper(params: dict[str, Any], **kwargs):
            # Get delegation token from params
            delegation_token = params.get("delegation_token")
            if not delegation_token:
                raise JsonRpcError(
                    -32602,
                    "Delegation token required",
                    {"user_message": "Delegationstoken kræves"}
                )
            
            # Verify token
            token = verify_delegation_token(delegation_token, self.action_type)
            if token is None:
                raise JsonRpcError(
                    -32603,
                    "Invalid delegation token",
                    {"user_message": "Ugyldigt delegationstoken"}
                )
            
            # Add token to params for the handler
            params["_delegation_token"] = token.to_dict()
            params["_delegator_id"] = token.delegator_id
            params["_delegatee_id"] = token.delegatee_id
            
            return handler(params, **kwargs)
        
        return wrapper


# Convenience function for creating delegated handlers
def delegated_handler(action_type: str):
    """Decorator for handlers that require delegation."""
    return DelegationMiddleware(action_type)
