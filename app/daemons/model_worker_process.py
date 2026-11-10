"""Model Worker Process - Isolated process for model execution.

This module implements the actual model execution processes that run
with separate isolation from the modeld gateway.

Security:
- Runs as user:group = eira-model:eira-models
- AppArmor profile: usr.bin.eira-model-worker (ultra-strict)
- systemd service: eira-model-worker@.service (resource-limited)
- Network: AF_UNIX only (no external network)

Worker Types:
- script: Execute user-provided Python scripts
- mistral: Run Mistral AI models via local Ollama
- veritas: Process Veritas evidence
"""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import struct
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ipc.paths import run_dir
from app.ipc.socket_security import (
    PeerCredentialError,
    setup_unix_socket,
    validate_peer_credentials,
)

logger = logging.getLogger(__name__)

# Worker configuration
WORKER_TYPES = {"script", "mistral", "veritas"}

# Security limits (per worker)
MAX_REQUEST_BYTES = 4 * 1024 * 1024  # 4 MB
REQUEST_TIMEOUT = 30  # seconds
MAX_CONNECTIONS = 256

# Allowed UIDs for connections to worker
# Only modeld (eira) and root should be able to connect
ALLOWED_UIDS = frozenset({
    0,  # root
})

ALLOWED_GIDS = frozenset({
    0,  # root group
})

# Try to resolve eira user and groups
try:
    import pwd
    eira_uid = pwd.getpwnam("eira").pw_uid
    ALLOWED_UIDS = ALLOWED_UIDS | {eira_uid}
except (KeyError, ImportError):
    pass

try:
    import grp
    eira_gid = grp.getgrnam("eira").gr_gid
    ALLOWED_GIDS = ALLOWED_GIDS | {eira_gid}
except (KeyError, ImportError):
    pass

try:
    eira_models_gid = grp.getgrnam("eira-models").gr_gid
    ALLOWED_GIDS = ALLOWED_GIDS | {eira_models_gid}
except (KeyError, ImportError):
    pass


@dataclass(frozen=True)
class PeerCredentials:
    """Peer credentials from SO_PEERCRED."""
    pid: int
    uid: int
    gid: int


class WorkerError(Exception):
    """Raised when worker execution fails."""
    pass


class ModelWorkerServer:
    """Unix socket server for a model worker process.
    
    This server listens for requests from modeld and executes
    model operations in an isolated process.
    """
    
    def __init__(self, worker_type: str):
        if worker_type not in WORKER_TYPES:
            raise ValueError(f"Unknown worker type: {worker_type}. Valid types: {WORKER_TYPES}")
        
        self.worker_type = worker_type
        self.socket_path = str(run_dir() / f"model-{worker_type}.sock")
        self._server: socket.socket | None = None
        self._stop = threading.Event()
        self._connections: set[socket.socket] = set()
        self._connections_lock = threading.Lock()
        
        # Initialize handler based on worker type
        self._handler = self._create_handler(worker_type)
        
        logger.info(f"Initialized {worker_type} worker server")
    
    def _create_handler(self, worker_type: str) -> Callable[[dict, PeerCredentials], dict]:
        """Create the appropriate handler for the worker type."""
        if worker_type == "script":
            return self._handle_script
        elif worker_type == "mistral":
            return self._handle_mistral
        elif worker_type == "veritas":
            return self._handle_veritas
        else:
            raise ValueError(f"Unknown worker type: {worker_type}")
    
    def _validate_peer(self, peer: PeerCredentials) -> None:
        """Validate that the peer is authorized to connect.
        
        Only modeld (running as eira) should be able to connect to workers.
        """
        # Root is explicitly privileged
        if peer.uid == 0:
            return
        
        # Check if UID is in allowlist
        if peer.uid in ALLOWED_UIDS:
            return
        
        # Check if GID is in allowlist
        if peer.gid in ALLOWED_GIDS:
            return
        
        raise PeerCredentialError(
            f"Peer UID {peer.uid} or GID {peer.gid} is not authorized to connect to worker"
        )
    
    def _validate_request_size(self, request: dict) -> None:
        """Validate request size."""
        request_json = json.dumps(request)
        if len(request_json.encode('utf-8')) > MAX_REQUEST_BYTES:
            raise WorkerError(f"Request too large: {len(request_json)} bytes")
    
    def _handle_script(self, request: dict, peer: PeerCredentials) -> dict:
        """Handle script execution requests."""
        script_id = request.get("script_id")
        input_data = request.get("input", {})
        
        if not script_id or not isinstance(script_id, str):
            raise WorkerError("script_id is required")
        
        # TODO: Implement actual script execution
        # This should:
        # 1. Load the script from a safe location
        # 2. Validate the script
        # 3. Execute in a sandboxed environment
        # 4. Return the result
        
        logger.info(f"Executing script {script_id} for UID {peer.uid}")
        
        # Stub implementation for now
        return {
            "output": f"Script {script_id} executed successfully",
            "script_id": script_id,
            "input": input_data,
            "model_type": "script"
        }
    
    def _handle_mistral(self, request: dict, peer: PeerCredentials) -> dict:
        """Handle Mistral model requests via local Ollama."""
        model_name = request.get("model_name", "mistral")
        prompt = request.get("prompt")
        
        if not prompt or not isinstance(prompt, str):
            raise WorkerError("prompt is required")
        
        # TODO: Implement actual Mistral execution via Ollama Unix socket
        # This should:
        # 1. Connect to local Ollama server via Unix socket
        # 2. Send the prompt
        # 3. Receive the response
        # 4. Return the result
        
        logger.info(f"Executing Mistral {model_name} for UID {peer.uid}")
        
        # Stub implementation for now
        return {
            "output": f"Mistral {model_name} response",
            "model": model_name,
            "done": True,
            "model_type": "mistral"
        }
    
    def _handle_veritas(self, request: dict, peer: PeerCredentials) -> dict:
        """Handle Veritas evidence processing requests."""
        evidence = request.get("evidence")
        
        if not evidence:
            raise WorkerError("evidence is required")
        
        # TODO: Implement actual Veritas processing
        # This should:
        # 1. Process the evidence
        # 2. Generate trust scores
        # 3. Return the result
        
        logger.info(f"Processing Veritas evidence for UID {peer.uid}")
        
        # Stub implementation for now
        return {
            "result": "evidence_processed",
            "evidence_hash": "stub_hash",
            "model_type": "veritas"
        }
    
    def _handle_request(self, line: str, peer: PeerCredentials) -> str:
        """Handle a single JSON-RPC request line."""
        try:
            # Validate request size
            if len(line.encode('utf-8')) > MAX_REQUEST_BYTES:
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32602,
                        "message": "Request too large",
                        "data": {"user_message": "Anmodningen er for stor"}
                    }
                }) + "\n"
            
            # Parse JSON
            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": "Invalid JSON",
                        "data": {"user_message": "Ugyldig JSON"}
                    }
                }) + "\n"
            
            # Validate request structure
            if not isinstance(request, dict):
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32600,
                        "message": "Invalid request",
                        "data": {"user_message": "Ugyldig anmodning"}
                    }
                }) + "\n"
            
            # Get request ID
            req_id = request.get("id")
            
            # Validate jsonrpc version
            if request.get("jsonrpc") != "2.0":
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32600,
                        "message": "Invalid jsonrpc version",
                        "data": {"user_message": "Ugyldig jsonrpc version"}
                    }
                }) + "\n"
            
            # Get method
            method = request.get("method")
            if not method or not isinstance(method, str):
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32600,
                        "message": "Method is required",
                        "data": {"user_message": "Metode skal angives"}
                    }
                }) + "\n"
            
            # Get params
            params = request.get("params", {})
            if not isinstance(params, dict):
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": "Invalid params",
                        "data": {"user_message": "Ugyldige parametre"}
                    }
                }) + "\n"
            
            # Validate request size (params)
            self._validate_request_size(params)
            
            # Handle execute method
            if method == "worker.execute":
                try:
                    result = self._handler(params, peer)
                    return json.dumps({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": result
                    }) + "\n"
                except WorkerError as exc:
                    return json.dumps({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32603,
                            "message": str(exc),
                            "data": {"user_message": f"Fejl: {exc}"}
                        }
                    }) + "\n"
                except Exception as exc:
                    logger.exception(f"Unexpected error in worker {self.worker_type}")
                    return json.dumps({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32603,
                            "message": "Internal error",
                            "data": {"user_message": "Intern fejl i worker"}
                        }
                    }) + "\n"
            
            # Handle health method
            elif method == "worker.health":
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "worker_type": self.worker_type,
                        "status": "healthy"
                    }
                }) + "\n"
            
            # Unknown method
            else:
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown method: {method}",
                        "data": {"user_message": f"Ukendt metode: {method}"}
                    }
                }) + "\n"
            
        except Exception as exc:
            logger.exception(f"Error handling request: {exc}")
            return json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32603,
                    "message": "Internal server error",
                    "data": {"user_message": "Intern serverfejl"}
                }
            }) + "\n"
    
    def _serve_client(self, conn: socket.socket) -> None:
        """Serve a connected client."""
        try:
            # Get peer credentials
            peer = validate_peer_credentials(conn, allowed_uids=ALLOWED_UIDS, allowed_gids=ALLOWED_GIDS)
            
            # Validate peer
            self._validate_peer(peer)
            
            with conn:
                buffer = b""
                while not self._stop.is_set():
                    try:
                        chunk = conn.recv(65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    buffer += chunk
                    if len(buffer) > MAX_REQUEST_BYTES and b"\n" not in buffer:
                        conn.sendall(
                            json.dumps({
                                "jsonrpc": "2.0",
                                "id": None,
                                "error": {
                                    "code": -32602,
                                    "message": "Request too large",
                                    "data": {"user_message": "Anmodningen er for stor"}
                                }
                            }).encode("utf-8") + b"\n"
                        )
                        return
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if not line.strip():
                            continue
                        response = self._handle_request(line.decode("utf-8"), peer)
                        conn.sendall(response.encode("utf-8"))
        except (PeerCredentialError, OSError) as exc:
            logger.warning(f"Client connection error: {exc}")
            conn.close()
        finally:
            with self._connections_lock:
                self._connections.discard(conn)
    
    def start(self) -> None:
        """Start the worker server."""
        # Ensure run directory exists
        run_dir().mkdir(parents=True, exist_ok=True)
        
        # Create and bind socket
        server = setup_unix_socket(self.socket_path, mode=0o660, group="eira-models")
        self._server = server
        server.listen(MAX_CONNECTIONS)
        server.settimeout(0.5)
        
        logger.info(f"Worker {self.worker_type} listening on {self.socket_path}")
        
        # Start accepting connections
        try:
            while not self._stop.is_set():
                try:
                    conn, _ = server.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                
                with self._connections_lock:
                    self._connections.add(conn)
                
                threading.Thread(
                    target=self._serve_client,
                    args=(conn,),
                    daemon=True,
                ).start()
        finally:
            self.stop()
    
    def stop(self) -> None:
        """Stop the worker server."""
        self._stop.set()
        
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        
        with self._connections_lock:
            connections = tuple(self._connections)
        for conn in connections:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()
        self._connections.clear()


def main() -> int:
    """Main entry point for model worker process."""
    import argparse
    
    parser = argparse.ArgumentParser(description="EiraOS Model Worker Process")
    parser.add_argument(
        "worker_type",
        choices=list(WORKER_TYPES),
        help="Type of worker to run"
    )
    parser.add_argument(
        "--socket-dir",
        default=str(run_dir()),
        help="Directory for Unix sockets"
    )
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Create and start server
    server = ModelWorkerServer(args.worker_type)
    
    # Handle shutdown signals
    def handle_shutdown(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}, shutting down...")
        server.stop()
    
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    try:
        server.start()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logger.exception(f"Worker failed: {exc}")
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
