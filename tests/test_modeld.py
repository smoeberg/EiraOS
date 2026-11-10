"""Tests for the model gateway daemon (modeld)."""

import json
import os
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app.daemons.modeld import (
    ALLOWED_GIDS,
    ALLOWED_UIDS,
    MAX_REQUEST_BYTES,
    ModelGateway,
    ModelWorker,
    ModelWorkerError,
    PeerCredentials,
    ScriptWorker,
    MistralWorker,
    VeritasWorker,
    get_gateway,
    register_model_handlers,
)
from app.ipc.jsonrpc import JsonRpcError


class TestPeerCredentials:
    """Tests for PeerCredentials dataclass."""
    
    def test_peer_credentials_creation(self):
        """Test creating peer credentials."""
        peer = PeerCredentials(pid=123, uid=1000, gid=1000)
        assert peer.pid == 123
        assert peer.uid == 1000
        assert peer.gid == 1000
    
    def test_peer_credentials_immutable(self):
        """Test that PeerCredentials is immutable."""
        peer = PeerCredentials(pid=123, uid=1000, gid=1000)
        with pytest.raises(AttributeError):
            peer.pid = 456


class TestModelGateway:
    """Tests for ModelGateway class."""
    
    def test_gateway_initialization(self):
        """Test gateway initialization."""
        gateway = ModelGateway()
        assert gateway is not None
        assert len(gateway.list_workers()) == 0
    
    def test_register_worker(self):
        """Test registering a worker."""
        gateway = ModelGateway()
        worker = ScriptWorker()
        gateway.register_worker("script", worker)
        
        assert "script" in gateway.list_workers()
        assert gateway.get_worker("script") is worker
    
    def test_get_unknown_worker(self):
        """Test getting an unknown worker raises ValueError."""
        gateway = ModelGateway()
        with pytest.raises(ValueError, match="Unknown worker type"):
            gateway.get_worker("unknown")
    
    def test_validate_peer_root(self):
        """Test that root peer is always allowed."""
        gateway = ModelGateway()
        peer = PeerCredentials(pid=1, uid=0, gid=0)
        gateway._validate_peer(peer)  # Should not raise
    
    def test_validate_peer_allowed_uid(self):
        """Test that allowed UIDs are accepted."""
        gateway = ModelGateway()
        # Add a test UID to allowed list
        test_uid = 9999
        original_allowed = ALLOWED_UIDS
        
        try:
            # Temporarily add test UID
            import app.daemons.modeld as modeld_module
            modeld_module.ALLOWED_UIDS = original_allowed | {test_uid}
            
            peer = PeerCredentials(pid=1, uid=test_uid, gid=0)
            gateway._validate_peer(peer)  # Should not raise
        finally:
            modeld_module.ALLOWED_UIDS = original_allowed
    
    def test_validate_peer_allowed_gid(self):
        """Test that allowed GIDs are accepted."""
        gateway = ModelGateway()
        # Add a test GID to allowed list
        test_gid = 9999
        original_allowed = ALLOWED_GIDS
        
        try:
            # Temporarily add test GID
            import app.daemons.modeld as modeld_module
            modeld_module.ALLOWED_GIDS = original_allowed | {test_gid}
            
            peer = PeerCredentials(pid=1, uid=1000, gid=test_gid)
            gateway._validate_peer(peer)  # Should not raise
        finally:
            modeld_module.ALLOWED_GIDS = original_allowed
    
    def test_validate_peer_unauthorized(self):
        """Test that unauthorized peers are rejected."""
        gateway = ModelGateway()
        peer = PeerCredentials(pid=1, uid=99999, gid=99999)
        
        with pytest.raises(Exception) as exc_info:
            gateway._validate_peer(peer)
        
        assert "not authorized" in str(exc_info.value)
    
    def test_validate_request_size_ok(self):
        """Test that valid request size passes validation."""
        gateway = ModelGateway()
        request = {"model_type": "script", "input": "test"}
        gateway._validate_request_size(request)  # Should not raise
    
    def test_validate_request_size_too_large(self):
        """Test that too large request is rejected."""
        gateway = ModelGateway()
        # Create a request larger than MAX_REQUEST_BYTES
        large_input = "x" * (MAX_REQUEST_BYTES + 100)
        request = {"model_type": "script", "input": large_input}
        
        with pytest.raises(JsonRpcError) as exc_info:
            gateway._validate_request_size(request)
        
        assert exc_info.value.code == -32602  # INVALID_PARAMS
        assert "too large" in str(exc_info.value).lower()
    
    def test_execute_model_missing_model_type(self):
        """Test that missing model_type raises error."""
        gateway = ModelGateway()
        worker = ScriptWorker()
        gateway.register_worker("script", worker)
        
        peer = PeerCredentials(pid=1, uid=0, gid=0)
        params = {"input": "test"}  # Missing model_type
        
        with pytest.raises(JsonRpcError) as exc_info:
            gateway.execute_model(params, peer)
        
        assert exc_info.value.code == -32602  # INVALID_PARAMS
    
    def test_execute_model_unknown_worker(self):
        """Test that unknown worker type raises error."""
        gateway = ModelGateway()
        peer = PeerCredentials(pid=1, uid=0, gid=0)
        params = {"model_type": "unknown"}
        
        with pytest.raises(JsonRpcError) as exc_info:
            gateway.execute_model(params, peer)
        
        assert exc_info.value.code == -32602  # INVALID_PARAMS


class TestModelWorker:
    """Tests for ModelWorker base class."""
    
    def test_worker_initialization(self):
        """Test worker initialization."""
        worker = ModelWorker("test")
        assert worker.worker_type == "test"
        assert "model-test.sock" in worker._socket_path
    
    def test_worker_execute_not_implemented(self):
        """Test that base worker raises NotImplementedError."""
        worker = ModelWorker("test")
        peer = PeerCredentials(pid=1, uid=0, gid=0)
        
        with pytest.raises(NotImplementedError):
            worker.execute({}, peer)
    
    def test_worker_health(self):
        """Test worker health check."""
        worker = ModelWorker("test")
        health = worker.health()
        
        assert health["worker_type"] == "test"
        assert health["status"] == "healthy"


class TestScriptWorker:
    """Tests for ScriptWorker."""
    
    def test_script_worker_initialization(self):
        """Test script worker initialization."""
        worker = ScriptWorker()
        assert worker.worker_type == "script"
    
    def test_script_worker_execute_missing_script_id(self):
        """Test that missing script_id raises error."""
        worker = ScriptWorker()
        peer = PeerCredentials(pid=1, uid=0, gid=0)
        params = {"input": "test"}  # Missing script_id
        
        with pytest.raises(ModelWorkerError, match="script_id is required"):
            worker.execute(params, peer)
    
    def test_script_worker_execute_stub(self):
        """Test that script worker returns stub response."""
        worker = ScriptWorker()
        peer = PeerCredentials(pid=1, uid=0, gid=0)
        params = {"script_id": "test-script", "input": {"key": "value"}}
        
        result = worker.execute(params, peer)
        
        assert "output" in result
        assert result["script_id"] == "test-script"
        assert result["model_type"] == "script"


class TestMistralWorker:
    """Tests for MistralWorker."""
    
    def test_mistral_worker_initialization(self):
        """Test mistral worker initialization."""
        worker = MistralWorker()
        assert worker.worker_type == "mistral"
    
    def test_mistral_worker_execute_missing_prompt(self):
        """Test that missing prompt raises error."""
        worker = MistralWorker()
        peer = PeerCredentials(pid=1, uid=0, gid=0)
        params = {"model_name": "mistral"}  # Missing prompt
        
        with pytest.raises(ModelWorkerError, match="prompt is required"):
            worker.execute(params, peer)
    
    def test_mistral_worker_execute_stub(self):
        """Test that mistral worker returns stub response."""
        worker = MistralWorker()
        peer = PeerCredentials(pid=1, uid=0, gid=0)
        params = {"model_name": "mistral", "prompt": "Test prompt"}
        
        result = worker.execute(params, peer)
        
        assert "output" in result
        assert result["model"] == "mistral"
        assert result["done"] is True
        assert result["model_type"] == "mistral"


class TestVeritasWorker:
    """Tests for VeritasWorker."""
    
    def test_veritas_worker_initialization(self):
        """Test veritas worker initialization."""
        worker = VeritasWorker()
        assert worker.worker_type == "veritas"
    
    def test_veritas_worker_execute_missing_evidence(self):
        """Test that missing evidence raises error."""
        worker = VeritasWorker()
        peer = PeerCredentials(pid=1, uid=0, gid=0)
        params = {}  # Missing evidence
        
        with pytest.raises(ModelWorkerError, match="evidence is required"):
            worker.execute(params, peer)
    
    def test_veritas_worker_execute_stub(self):
        """Test that veritas worker returns stub response."""
        worker = VeritasWorker()
        peer = PeerCredentials(pid=1, uid=0, gid=0)
        params = {"evidence": "test evidence"}
        
        result = worker.execute(params, peer)
        
        assert result["result"] == "evidence_processed"
        assert result["model_type"] == "veritas"


class TestGetGateway:
    """Tests for get_gateway function."""
    
    def test_get_gateway_singleton(self):
        """Test that get_gateway returns the same instance."""
        gateway1 = get_gateway()
        gateway2 = get_gateway()
        assert gateway1 is gateway2
    
    def test_get_gateway_initializes_workers(self):
        """Test that get_gateway initializes default workers."""
        gateway = get_gateway()
        workers = gateway.list_workers()
        
        assert "script" in workers
        assert "mistral" in workers
        assert "veritas" in workers


class TestRegisterModelHandlers:
    """Tests for register_model_handlers function."""
    
    def test_register_model_handlers(self):
        """Test that model handlers are registered correctly."""
        from app.daemons.base import JsonRpcServer
        
        server = JsonRpcServer(name="test", daemon="test")
        register_model_handlers(server)
        
        # Check that handlers are registered
        assert "model.execute" in server._handlers
        assert "model.list" in server._handlers
        assert "model.health" in server._handlers
        assert "health" in server._handlers
        
        # Check that model.execute wants peer
        assert server._handlers["model.execute"].wants_peer is True


class TestConcurrentRequests:
    """Tests for concurrent request handling."""
    
    def test_concurrent_requests(self):
        """Test that gateway can handle concurrent requests."""
        gateway = get_gateway()
        peer = PeerCredentials(pid=1, uid=0, gid=0)
        
        # Register a simple worker
        class TestWorker(ModelWorker):
            def __init__(self):
                super().__init__("test")
            
            def execute(self, params, peer):
                time.sleep(0.1)  # Simulate processing time
                return {"result": "ok"}
        
        gateway.register_worker("test", TestWorker())
        
        # Submit multiple concurrent requests
        results = []
        errors = []
        
        def execute_request(i):
            try:
                params = {"model_type": "test", "input": f"test {i}"}
                result = gateway.execute_model(params, peer)
                results.append(result)
            except Exception as exc:
                errors.append(exc)
        
        threads = []
        for i in range(10):
            t = threading.Thread(target=execute_request, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(results) == 10
        assert len(errors) == 0
