"""Tests for the model worker process."""

import json
import os
import socket
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.daemons.model_worker_process import (
    ALLOWED_GIDS,
    ALLOWED_UIDS,
    MAX_REQUEST_BYTES,
    ModelWorkerServer,
    PeerCredentials,
    WorkerError,
)


class TestModelWorkerServer:
    """Tests for ModelWorkerServer class."""
    
    def test_server_initialization(self):
        """Test server initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                assert server.worker_type == "script"
                assert "model-script.sock" in server.socket_path
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_server_invalid_worker_type(self):
        """Test that invalid worker type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown worker type"):
            ModelWorkerServer("invalid")
    
    def test_server_valid_worker_types(self):
        """Test that all valid worker types are accepted."""
        for worker_type in ["script", "mistral", "veritas"]:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.environ["EIRA_RUN_DIR"] = tmpdir
                
                try:
                    server = ModelWorkerServer(worker_type)
                    assert server.worker_type == worker_type
                finally:
                    del os.environ["EIRA_RUN_DIR"]
    
    def test_handler_creation(self):
        """Test that handlers are created for each worker type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                for worker_type in ["script", "mistral", "veritas"]:
                    server = ModelWorkerServer(worker_type)
                    assert server._handler is not None
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_validate_peer_root(self):
        """Test that root peer is always allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                peer = PeerCredentials(pid=1, uid=0, gid=0)
                server._validate_peer(peer)  # Should not raise
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_validate_peer_allowed_uid(self):
        """Test that allowed UIDs are accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                # Add a test UID to allowed list
                test_uid = 9999
                original_allowed = ALLOWED_UIDS
                
                # Temporarily add test UID
                import app.daemons.model_worker_process as worker_module
                worker_module.ALLOWED_UIDS = original_allowed | {test_uid}
                
                peer = PeerCredentials(pid=1, uid=test_uid, gid=0)
                server._validate_peer(peer)  # Should not raise
            finally:
                worker_module.ALLOWED_UIDS = original_allowed
                del os.environ["EIRA_RUN_DIR"]
    
    def test_validate_peer_unauthorized(self):
        """Test that unauthorized peers are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                peer = PeerCredentials(pid=1, uid=99999, gid=99999)
                
                with pytest.raises(Exception) as exc_info:
                    server._validate_peer(peer)
                
                assert "not authorized" in str(exc_info.value)
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_validate_request_size_ok(self):
        """Test that valid request size passes validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                request = {"script_id": "test", "input": "test"}
                server._validate_request_size(request)  # Should not raise
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_validate_request_size_too_large(self):
        """Test that too large request is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                large_input = "x" * (MAX_REQUEST_BYTES + 100)
                request = {"script_id": "test", "input": large_input}
                
                with pytest.raises(WorkerError, match="Request too large"):
                    server._validate_request_size(request)
            finally:
                del os.environ["EIRA_RUN_DIR"]


class TestHandlerMethods:
    """Tests for handler methods."""
    
    def test_script_handler_missing_script_id(self):
        """Test that script handler requires script_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                peer = PeerCredentials(pid=1, uid=0, gid=0)
                request = {"input": "test"}  # Missing script_id
                
                with pytest.raises(WorkerError, match="script_id is required"):
                    server._handle_script(request, peer)
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_script_handler_stub(self):
        """Test that script handler returns stub response."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                peer = PeerCredentials(pid=1, uid=0, gid=0)
                request = {"script_id": "test-script", "input": {"key": "value"}}
                
                result = server._handle_script(request, peer)
                
                assert "output" in result
                assert result["script_id"] == "test-script"
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_mistral_handler_missing_prompt(self):
        """Test that mistral handler requires prompt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("mistral")
                peer = PeerCredentials(pid=1, uid=0, gid=0)
                request = {"model_name": "mistral"}  # Missing prompt
                
                with pytest.raises(WorkerError, match="prompt is required"):
                    server._handle_mistral(request, peer)
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_mistral_handler_stub(self):
        """Test that mistral handler returns stub response."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("mistral")
                peer = PeerCredentials(pid=1, uid=0, gid=0)
                request = {"model_name": "mistral", "prompt": "Test prompt"}
                
                result = server._handle_mistral(request, peer)
                
                assert "output" in result
                assert result["model"] == "mistral"
                assert result["done"] is True
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_veritas_handler_missing_evidence(self):
        """Test that veritas handler requires evidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("veritas")
                peer = PeerCredentials(pid=1, uid=0, gid=0)
                request = {}  # Missing evidence
                
                with pytest.raises(WorkerError, match="evidence is required"):
                    server._handle_veritas(request, peer)
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_veritas_handler_stub(self):
        """Test that veritas handler returns stub response."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("veritas")
                peer = PeerCredentials(pid=1, uid=0, gid=0)
                request = {"evidence": "test evidence"}
                
                result = server._handle_veritas(request, peer)
                
                assert result["result"] == "evidence_processed"
            finally:
                del os.environ["EIRA_RUN_DIR"]


class TestRequestHandling:
    """Tests for JSON-RPC request handling."""
    
    def test_handle_request_valid_jsonrpc(self):
        """Test handling valid JSON-RPC request."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                peer = PeerCredentials(pid=1, uid=0, gid=0)
                
                request = json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "worker.health",
                    "params": {}
                })
                
                response = server._handle_request(request, peer)
                response_data = json.loads(response.strip())
                
                assert response_data["jsonrpc"] == "2.0"
                assert response_data["id"] == 1
                assert "result" in response_data
                assert response_data["result"]["worker_type"] == "script"
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_handle_request_invalid_json(self):
        """Test handling invalid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                peer = PeerCredentials(pid=1, uid=0, gid=0)
                
                request = "not valid json"
                
                response = server._handle_request(request, peer)
                response_data = json.loads(response.strip())
                
                assert response_data["jsonrpc"] == "2.0"
                assert response_data["id"] is None
                assert "error" in response_data
                assert response_data["error"]["code"] == -32700  # Parse error
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_handle_request_invalid_jsonrpc_version(self):
        """Test handling invalid jsonrpc version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                peer = PeerCredentials(pid=1, uid=0, gid=0)
                
                request = json.dumps({
                    "jsonrpc": "1.0",
                    "id": 1,
                    "method": "worker.health",
                    "params": {}
                })
                
                response = server._handle_request(request, peer)
                response_data = json.loads(response.strip())
                
                assert response_data["jsonrpc"] == "2.0"
                assert response_data["id"] == 1
                assert "error" in response_data
                assert response_data["error"]["code"] == -32600  # Invalid request
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_handle_request_missing_method(self):
        """Test handling request with missing method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                peer = PeerCredentials(pid=1, uid=0, gid=0)
                
                request = json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "params": {}
                })
                
                response = server._handle_request(request, peer)
                response_data = json.loads(response.strip())
                
                assert response_data["jsonrpc"] == "2.0"
                assert response_data["id"] == 1
                assert "error" in response_data
                assert response_data["error"]["code"] == -32600  # Invalid request
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_handle_request_unknown_method(self):
        """Test handling unknown method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                peer = PeerCredentials(pid=1, uid=0, gid=0)
                
                request = json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "unknown.method",
                    "params": {}
                })
                
                response = server._handle_request(request, peer)
                response_data = json.loads(response.strip())
                
                assert response_data["jsonrpc"] == "2.0"
                assert response_data["id"] == 1
                assert "error" in response_data
                assert response_data["error"]["code"] == -32601  # Method not found
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_handle_request_too_large(self):
        """Test handling too large request."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                peer = PeerCredentials(pid=1, uid=0, gid=0)
                
                # Create a request line larger than MAX_REQUEST_BYTES
                large_params = "x" * (MAX_REQUEST_BYTES + 100)
                request = json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "worker.health",
                    "params": large_params
                })
                
                response = server._handle_request(request, peer)
                response_data = json.loads(response.strip())
                
                assert response_data["jsonrpc"] == "2.0"
                assert response_data["id"] is None
                assert "error" in response_data
                assert response_data["error"]["code"] == -32602  # Invalid params
            finally:
                del os.environ["EIRA_RUN_DIR"]


class TestSocketOperations:
    """Tests for socket operations."""
    
    def test_start_stop(self):
        """Test starting and stopping the server."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                
                # Start server in a thread
                server_thread = threading.Thread(target=server.start)
                server_thread.daemon = True
                server_thread.start()
                
                # Wait for server to start
                time.sleep(0.5)
                
                # Check that socket exists (may not exist if group resolution fails)
                socket_path = Path(server.socket_path)
                if socket_path.exists():
                    # Stop server
                    server.stop()
                    server_thread.join(timeout=1.0)
                    
                    # Check that socket is removed
                    assert not socket_path.exists()
                else:
                    # Socket creation may have failed due to missing group
                    # This is acceptable for the test environment
                    server.stop()
                    server_thread.join(timeout=1.0)
            finally:
                del os.environ["EIRA_RUN_DIR"]
    
    def test_socket_permissions(self):
        """Test socket permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                server = ModelWorkerServer("script")
                
                # Start server in a thread
                server_thread = threading.Thread(target=server.start)
                server_thread.daemon = True
                server_thread.start()
                
                # Wait for server to start
                time.sleep(0.5)
                
                # Check socket permissions
                import stat
                socket_path = Path(server.socket_path)
                socket_stat = socket_path.stat()
                
                # Should be a socket
                assert stat.S_ISSOCK(socket_stat.st_mode)
                
                # Check mode (should be 0660)
                mode = stat.S_IMODE(socket_stat.st_mode)
                assert mode == 0o660
                
                # Stop server
                server.stop()
                server_thread.join(timeout=1.0)
            finally:
                del os.environ["EIRA_RUN_DIR"]


class TestMainFunction:
    """Tests for main function."""
    
    def test_main_invalid_worker_type(self):
        """Test main with invalid worker type."""
        import sys
        from unittest.mock import patch
        from io import StringIO
        
        # Mock sys.argv to pass invalid worker type
        # argparse will exit with code 2 for invalid choice
        with patch.object(sys, "argv", ["eira-model-worker", "invalid"]):
            with patch.object(sys, "stderr", StringIO()):
                from app.daemons.model_worker_process import main
                try:
                    result = main()
                    # If we get here, it should have exited with code 2
                    assert False, "Expected SystemExit"
                except SystemExit as e:
                    assert e.code == 2
    
    def test_main_valid_worker_type(self):
        """Test main with valid worker type (but don't actually start)."""
        import sys
        from unittest.mock import patch
        
        # Mock sys.argv to pass valid worker type
        # We'll patch the start method to avoid actually starting the server
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["EIRA_RUN_DIR"] = tmpdir
            
            try:
                with patch.object(sys, "argv", ["eira-model-worker", "script"]):
                    with patch("app.daemons.model_worker_process.ModelWorkerServer.start") as mock_start:
                        mock_start.return_value = None
                        from app.daemons.model_worker_process import main
                        result = main()
                        assert result == 0
                        mock_start.assert_called_once()
            finally:
                del os.environ["EIRA_RUN_DIR"]
