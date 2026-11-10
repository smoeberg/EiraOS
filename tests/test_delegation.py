"""Tests for the delegation protocol."""

import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.gate.delegation import (
    DELEGATABLE_ACTIONS,
    SCOPE_LEVELS,
    DelegationError,
    DelegationStore,
    DelegationToken,
    get_delegation_store,
    create_delegation_token,
    verify_delegation_token,
    revoke_delegation_token,
    list_delegation_tokens,
)


class TestDelegationToken:
    """Tests for DelegationToken dataclass."""
    
    def test_token_creation(self):
        """Test creating a delegation token."""
        token = DelegationToken(
            token_id="test-123",
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
        )
        
        assert token.token_id == "test-123"
        assert token.delegator_id == "user-1"
        assert token.delegatee_id == "model-1"
        assert token.action_type == "model.prepare"
        assert token.scope == "read"
        assert token.delegatee_type == "model"
    
    def test_token_expiration(self):
        """Test token expiration."""
        # Create expired token
        expired_token = DelegationToken(
            token_id="expired",
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        
        assert expired_token.is_expired() is True
        
        # Create valid token
        valid_token = DelegationToken(
            token_id="valid",
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        
        assert valid_token.is_expired() is False
    
    def test_token_action_validation(self):
        """Test token action validation."""
        token = DelegationToken(
            token_id="test",
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
        )
        
        assert token.is_valid_action("model.prepare") is True
        assert token.is_valid_action("intent.prepare") is False
    
    def test_token_to_dict(self):
        """Test converting token to dictionary."""
        now = datetime.now(timezone.utc)
        token = DelegationToken(
            token_id="test",
            delegator_id="user-1",
            delegator_name="Test User",
            delegatee_id="model-1",
            action_type="model.prepare",
            scope="write",
            resource_pattern="resource-*",
            created_at=now,
            expires_at=now + timedelta(hours=1),
            metadata={"key": "value"},
        )
        
        data = token.to_dict()
        
        assert data["token_id"] == "test"
        assert data["delegator_id"] == "user-1"
        assert data["delegator_name"] == "Test User"
        assert data["delegatee_id"] == "model-1"
        assert data["action_type"] == "model.prepare"
        assert data["scope"] == "write"
        assert data["resource_pattern"] == "resource-*"
        assert data["metadata"] == {"key": "value"}
    
    def test_token_from_dict(self):
        """Test creating token from dictionary."""
        now = datetime.now(timezone.utc)
        data = {
            "token_id": "test",
            "delegator_id": "user-1",
            "delegator_name": "Test User",
            "delegatee_id": "model-1",
            "action_type": "model.prepare",
            "scope": "write",
            "resource_pattern": "resource-*",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat(),
            "metadata": {"key": "value"},
        }
        
        token = DelegationToken.from_dict(data)
        
        assert token.token_id == "test"
        assert token.delegator_id == "user-1"
        assert token.delegatee_id == "model-1"
        assert token.action_type == "model.prepare"


class TestDelegationStore:
    """Tests for DelegationStore class."""
    
    def test_store_initialization(self):
        """Test store initialization."""
        store = DelegationStore()
        assert store._tokens == {}
        assert store._revoked == set()
        assert store._key is None
    
    def test_init_key(self):
        """Test key initialization."""
        store = DelegationStore()
        
        # Generate a key
        key = store.init_key()
        assert key is not None
        assert len(key) == 64  # 32 bytes hex encoded
        assert store._key == key
        
        # Use provided key
        provided_key = secrets.token_hex(32)
        store2 = DelegationStore()
        key2 = store2.init_key(provided_key)
        assert key2 == provided_key
        assert store2._key == provided_key
    
    def test_create_token(self):
        """Test creating a delegation token."""
        store = DelegationStore()
        store.init_key()
        
        token = store.create_token(
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
        )
        
        assert token.token_id is not None
        assert token.delegator_id == "user-1"
        assert token.delegatee_id == "model-1"
        assert token.action_type == "model.prepare"
        assert token.scope == "read"
        assert token in store._tokens.values()
    
    def test_create_token_with_all_params(self):
        """Test creating a token with all parameters."""
        store = DelegationStore()
        store.init_key()
        
        token = store.create_token(
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
            scope="write",
            resource_pattern="resource-*",
            ttl=timedelta(minutes=30),
            delegator_name="Test User",
            metadata={"key": "value"},
        )
        
        assert token.scope == "write"
        assert token.resource_pattern == "resource-*"
        assert token.delegator_name == "Test User"
        assert token.metadata == {"key": "value"}
    
    def test_create_token_validation(self):
        """Test token creation validation."""
        store = DelegationStore()
        store.init_key()
        
        # Missing delegator_id
        with pytest.raises(DelegationError, match="delegator_id is required"):
            store.create_token(
                delegator_id=None,
                delegatee_id="model-1",
                action_type="model.prepare",
            )
        
        # Missing delegatee_id
        with pytest.raises(DelegationError, match="delegatee_id is required"):
            store.create_token(
                delegator_id="user-1",
                delegatee_id=None,
                action_type="model.prepare",
            )
        
        # Missing action_type
        with pytest.raises(DelegationError, match="action_type is required"):
            store.create_token(
                delegator_id="user-1",
                delegatee_id="model-1",
                action_type=None,
            )
        
        # Invalid action_type
        with pytest.raises(DelegationError, match="action_type must be one of"):
            store.create_token(
                delegator_id="user-1",
                delegatee_id="model-1",
                action_type="invalid.action",
            )
        
        # Invalid scope
        with pytest.raises(DelegationError, match="scope must be one of"):
            store.create_token(
                delegator_id="user-1",
                delegatee_id="model-1",
                action_type="model.prepare",
                scope="invalid",
            )
        
        # TTL too long
        with pytest.raises(DelegationError, match="TTL cannot exceed"):
            store.create_token(
                delegator_id="user-1",
                delegatee_id="model-1",
                action_type="model.prepare",
                ttl=timedelta(hours=2),  # More than max
            )
    
    def test_get_token(self):
        """Test getting a token."""
        store = DelegationStore()
        store.init_key()
        
        token = store.create_token(
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
        )
        
        # Get valid token
        retrieved = store.get_token(token.token_id)
        assert retrieved is not None
        assert retrieved.token_id == token.token_id
        
        # Get non-existent token
        assert store.get_token("non-existent") is None
        
        # Get expired token
        expired_token = DelegationToken(
            token_id="expired",
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        store._tokens["expired"] = expired_token
        assert store.get_token("expired") is None
    
    def test_validate_token(self):
        """Test token validation."""
        store = DelegationStore()
        store.init_key()
        
        token = store.create_token(
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
        )
        
        # Valid action
        assert store.validate_token(token.token_id, "model.prepare") is True
        
        # Invalid action
        assert store.validate_token(token.token_id, "intent.prepare") is False
        
        # Non-existent token
        assert store.validate_token("non-existent", "model.prepare") is False
    
    def test_revoke_token(self):
        """Test revoking a token."""
        store = DelegationStore()
        store.init_key()
        
        token = store.create_token(
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
        )
        
        # Token should be valid
        assert store.get_token(token.token_id) is not None
        
        # Revoke token
        assert store.revoke_token(token.token_id) is True
        
        # Token should no longer be valid
        assert store.get_token(token.token_id) is None
        
        # Revoke non-existent token
        assert store.revoke_token("non-existent") is False
    
    def test_revoke_by_delegator(self):
        """Test revoking all tokens for a delegator."""
        store = DelegationStore()
        store.init_key()
        
        # Create multiple tokens
        token1 = store.create_token(
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
        )
        token2 = store.create_token(
            delegator_id="user-1",
            delegatee_id="model-2",
            action_type="model.prepare",
        )
        token3 = store.create_token(
            delegator_id="user-2",
            delegatee_id="model-1",
            action_type="model.prepare",
        )
        
        # Revoke all tokens for user-1
        count = store.revoke_by_delegator("user-1")
        assert count == 2
        
        # Check that user-1's tokens are revoked
        assert store.get_token(token1.token_id) is None
        assert store.get_token(token2.token_id) is None
        
        # Check that user-2's token is still valid
        assert store.get_token(token3.token_id) is not None
    
    def test_revoke_by_delegatee(self):
        """Test revoking all tokens for a delegatee."""
        store = DelegationStore()
        store.init_key()
        
        # Create multiple tokens
        token1 = store.create_token(
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
        )
        token2 = store.create_token(
            delegator_id="user-2",
            delegatee_id="model-1",
            action_type="model.prepare",
        )
        token3 = store.create_token(
            delegator_id="user-1",
            delegatee_id="model-2",
            action_type="model.prepare",
        )
        
        # Revoke all tokens for model-1
        count = store.revoke_by_delegatee("model-1")
        assert count == 2
        
        # Check that model-1's tokens are revoked
        assert store.get_token(token1.token_id) is None
        assert store.get_token(token2.token_id) is None
        
        # Check that model-2's token is still valid
        assert store.get_token(token3.token_id) is not None
    
    def test_list_tokens(self):
        """Test listing tokens."""
        store = DelegationStore()
        store.init_key()
        
        # Create tokens
        token1 = store.create_token(
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
        )
        token2 = store.create_token(
            delegator_id="user-2",
            delegatee_id="model-1",
            action_type="model.prepare",
        )
        
        # List all tokens
        all_tokens = store.list_tokens()
        assert len(all_tokens) == 2
        
        # List tokens for specific delegator
        user1_tokens = store.list_tokens(delegator_id="user-1")
        assert len(user1_tokens) == 1
        assert user1_tokens[0].token_id == token1.token_id


class TestTokenSigning:
    """Tests for token signing and verification."""
    
    def test_sign_and_verify_token(self):
        """Test signing and verifying a token."""
        store = DelegationStore()
        key = secrets.token_hex(32)
        store.init_key(key)
        
        token = store.create_token(
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
        )
        
        # Sign token
        signed = store.sign_token(token)
        assert ":" in signed
        token_id, signature = signed.split(":", 1)
        assert token_id == token.token_id
        assert len(signature) == 64  # SHA256 hex
        
        # Verify token
        verified = store.verify_token(signed)
        assert verified is not None
        assert verified.token_id == token.token_id
    
    def test_verify_invalid_signature(self):
        """Test verifying a token with invalid signature."""
        store = DelegationStore()
        key = secrets.token_hex(32)
        store.init_key(key)
        
        token = store.create_token(
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
        )
        
        # Create invalid signature
        signed = f"{token.token_id}:invalid-signature"
        
        # Verify should fail
        assert store.verify_token(signed) is None
    
    def test_verify_expired_token(self):
        """Test verifying an expired token."""
        store = DelegationStore()
        key = secrets.token_hex(32)
        store.init_key(key)
        
        # Create expired token
        expired_token = DelegationToken(
            token_id="expired",
            delegator_id="user-1",
            delegatee_id="model-1",
            action_type="model.prepare",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        store._tokens["expired"] = expired_token
        
        # Sign token
        signed = store.sign_token(expired_token)
        
        # Verify should fail (token expired)
        assert store.verify_token(signed) is None


class TestGlobalFunctions:
    """Tests for global delegation functions."""
    
    def test_get_delegation_store_singleton(self):
        """Test that get_delegation_store returns the same instance."""
        store1 = get_delegation_store()
        store2 = get_delegation_store()
        assert store1 is store2
    
    def test_create_delegation_token(self):
        """Test creating a delegation token via global function."""
        # Set a key for testing
        key = secrets.token_hex(32)
        with patch.dict(os.environ, {"EIRA_DELEGATION_KEY": key}):
            # Reset the global store
            import app.gate.delegation as delegation_module
            delegation_module._delegation_store = None
            
            signed_token = create_delegation_token(
                delegator_id="user-1",
                delegatee_id="model-1",
                action_type="model.prepare",
            )
            
            assert ":" in signed_token
            token_id, signature = signed_token.split(":", 1)
            assert len(signature) == 64
    
    def test_verify_delegation_token(self):
        """Test verifying a delegation token via global function."""
        # Set a key for testing
        key = secrets.token_hex(32)
        with patch.dict(os.environ, {"EIRA_DELEGATION_KEY": key}):
            # Reset the global store
            import app.gate.delegation as delegation_module
            delegation_module._delegation_store = None
            
            # Create token
            signed_token = create_delegation_token(
                delegator_id="user-1",
                delegatee_id="model-1",
                action_type="model.prepare",
            )
            
            # Verify token
            token = verify_delegation_token(signed_token, "model.prepare")
            assert token is not None
            assert token.delegator_id == "user-1"
            assert token.delegatee_id == "model-1"
    
    def test_revoke_delegation_token(self):
        """Test revoking a delegation token via global function."""
        # Set a key for testing
        key = secrets.token_hex(32)
        with patch.dict(os.environ, {"EIRA_DELEGATION_KEY": key}):
            # Reset the global store
            import app.gate.delegation as delegation_module
            delegation_module._delegation_store = None
            
            # Create token
            signed_token = create_delegation_token(
                delegator_id="user-1",
                delegatee_id="model-1",
                action_type="model.prepare",
            )
            
            # Get token ID
            token_id = signed_token.split(":")[0]
            
            # Revoke token
            assert revoke_delegation_token(token_id) is True
            
            # Verify token should fail
            assert verify_delegation_token(signed_token, "model.prepare") is None
    
    def test_list_delegation_tokens(self):
        """Test listing delegation tokens via global function."""
        # Set a key for testing
        key = secrets.token_hex(32)
        with patch.dict(os.environ, {"EIRA_DELEGATION_KEY": key}):
            # Reset the global store
            import app.gate.delegation as delegation_module
            delegation_module._delegation_store = None
            
            # Create tokens
            create_delegation_token(
                delegator_id="user-1",
                delegatee_id="model-1",
                action_type="model.prepare",
            )
            create_delegation_token(
                delegator_id="user-2",
                delegatee_id="model-1",
                action_type="model.prepare",
            )
            
            # List tokens
            tokens = list_delegation_tokens()
            assert len(tokens) == 2


class TestDelegationMiddleware:
    """Tests for delegation middleware."""
    
    def test_middleware_valid_token(self):
        """Test middleware with valid token."""
        from app.gate.delegation import DelegationMiddleware
        
        # Set a key for testing
        key = secrets.token_hex(32)
        with patch.dict(os.environ, {"EIRA_DELEGATION_KEY": key}):
            # Reset the global store
            import app.gate.delegation as delegation_module
            delegation_module._delegation_store = None
            
            # Create a signed token
            signed_token = create_delegation_token(
                delegator_id="user-1",
                delegatee_id="model-1",
                action_type="model.prepare",
            )
            
            # Create middleware
            middleware = DelegationMiddleware("model.prepare")
            
            # Create a simple handler
            def handler(params, **kwargs):
                return {"success": True}
            
            # Wrap handler
            wrapped = middleware(handler)
            
            # Call with valid token
            result = wrapped({"delegation_token": signed_token})
            assert result["success"] is True
    
    def test_middleware_missing_token(self):
        """Test middleware with missing token."""
        from app.gate.delegation import DelegationMiddleware
        from app.ipc.jsonrpc import JsonRpcError
        
        # Create middleware
        middleware = DelegationMiddleware("model.prepare")
        
        # Create a simple handler
        def handler(params, **kwargs):
            return {"success": True}
        
        # Wrap handler
        wrapped = middleware(handler)
        
        # Call without token
        with pytest.raises(JsonRpcError) as exc_info:
            wrapped({})
        
        assert exc_info.value.code == -32602  # INVALID_PARAMS
    
    def test_middleware_invalid_token(self):
        """Test middleware with invalid token."""
        from app.gate.delegation import DelegationMiddleware
        from app.ipc.jsonrpc import JsonRpcError
        
        # Create middleware
        middleware = DelegationMiddleware("model.prepare")
        
        # Create a simple handler
        def handler(params, **kwargs):
            return {"success": True}
        
        # Wrap handler
        wrapped = middleware(handler)
        
        # Call with invalid token
        with pytest.raises(JsonRpcError) as exc_info:
            wrapped({"delegation_token": "invalid-token"})
        
        assert exc_info.value.code == -32603  # INTERNAL_ERROR


class TestDelegationConstants:
    """Tests for delegation constants."""
    
    def test_delegatable_actions(self):
        """Test delegatable actions."""
        assert "model.prepare" in DELEGATABLE_ACTIONS
        assert "intent.prepare" in DELEGATABLE_ACTIONS
        assert "action.prepare" in DELEGATABLE_ACTIONS
        assert "consent.prepare" in DELEGATABLE_ACTIONS
    
    def test_scope_levels(self):
        """Test scope levels."""
        assert "read" in SCOPE_LEVELS
        assert "write" in SCOPE_LEVELS
        assert "admin" in SCOPE_LEVELS
