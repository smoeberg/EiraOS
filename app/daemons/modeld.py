"""Model Gateway Daemon - IPC Gateway for Model Operations.

This daemon is ONLY an IPC gateway. It does NOT execute model code.
Model execution happens in separate worker processes with their own isolation.

Security:
- Validates SO_PEERCRED (UID/GID) for all connections
- Enforces input limits (size, timeout)
- Routes requests to appropriate workers
- Audit logs all operations to stated daemon

Architecture:
- modeld (this daemon): IPC gateway, runs as user:group = eira:eira
- Workers: Separate processes, run as user:group = eira-model:eira-models
- Communication: Unix sockets via /run/eira/
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.daemons.base import JsonRpcServer
from app.ipc.auth import PEER_KEY, strip_and_validate_ipc_auth
from app.ipc.jsonrpc import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    JsonRpcError,
    error_response,
    success_response,
)
from app.ipc.paths import run_dir
from app.ipc.socket_security import (
    PeerCredentialError,
    validate_peer_credentials,
)

logger = logging.getLogger(__name__)

# Security limits
MAX_REQUEST_BYTES = 4 * 1024 * 1024  # 4 MB
REQUEST_TIMEOUT = 30  # seconds
MAX_CONCURRENT_REQUESTS = 100

# Allowed UIDs and GIDs for IPC access
ALLOWED_UIDS = frozenset({
    0,  # root
    os.getuid(),  # current user (for development)
})

ALLOWED_GIDS = frozenset({
    os.getgid(),  # current group (for development)
})

# Try to resolve eira group
try:
    import grp
    eira_gid = grp.getgrnam("eira").gr_gid
    ALLOWED_GIDS = ALLOWED_GIDS | {eira_gid}
except (KeyError, ImportError):
    pass

try:
    eira_clients_gid = grp.getgrnam("eira-clients").gr_gid
    ALLOWED_GIDS = ALLOWED_GIDS | {eira_clients_gid}
except (KeyError, ImportError):
    pass

try:
    eira_model_uid = None
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


class ModelWorkerError(Exception):
    """Raised when a model worker fails to execute."""
    pass


class ModelGateway:
    """Model Gateway - IPC Gateway for Model Operations.
    
    This class is the central gateway for all model-related IPC requests.
    It validates peers, enforces limits, routes to workers, and logs audits.
    """
    
    def __init__(self):
        self._workers: dict[str, ModelWorker] = {}
        self._worker_lock = threading.Lock()
        self._request_counter = 0
        self._request_lock = threading.Lock()
        self._audit_client = None
        self._stated_socket = None
    
    def register_worker(self, worker_type: str, worker: ModelWorker) -> None:
        """Register a model worker for a specific type."""
        with self._worker_lock:
            self._workers[worker_type] = worker
        logger.info(f"Registered worker for type: {worker_type}")
    
    def get_worker(self, worker_type: str) -> ModelWorker:
        """Get a registered worker by type."""
        with self._worker_lock:
            worker = self._workers.get(worker_type)
        if worker is None:
            raise ValueError(f"Unknown worker type: {worker_type}")
        return worker
    
    def list_workers(self) -> list[str]:
        """List all registered worker types."""
        with self._worker_lock:
            return list(self._workers.keys())
    
    def _validate_peer(self, peer: PeerCredentials) -> None:
        """Validate peer credentials against allowlist (fail closed)."""
        # Root is explicitly privileged
        if peer.uid == 0:
            return
        
        # Check if UID is in allowlist
        if peer.uid in ALLOWED_UIDS:
            return
        
        # Check if GID or any supplementary group is in allowlist
        # For now, we only have the primary GID from SO_PEERCRED
        # Supplementary groups would require SO_PEERGROUPS
        if peer.gid in ALLOWED_GIDS:
            return
        
        raise PeerCredentialError(
            f"Peer UID {peer.uid} or GID {peer.gid} is not authorized"
        )
    
    def _validate_request_size(self, request: dict) -> None:
        """Validate that request size is within limits."""
        request_json = json.dumps(request)
        if len(request_json.encode('utf-8')) > MAX_REQUEST_BYTES:
            raise JsonRpcError(
                INVALID_PARAMS,
                "Request too large",
                {"user_message": f"Anmodningen er for stor (maksimum {MAX_REQUEST_BYTES // 1024 // 1024} MB)"}
            )
    
    def _get_next_request_id(self) -> int:
        """Get the next request ID."""
        with self._request_lock:
            self._request_counter += 1
            return self._request_counter
    
    def _log_audit(self, action: str, session_id: str | None, model_type: str, 
                   peer: PeerCredentials, result: str, execution_time_ms: float,
                   **extra) -> None:
        """Log an audit event to the stated daemon."""
        if self._audit_client is None:
            # Lazy initialization
            try:
                from app.ipc.client import IpcClient
                self._audit_client = IpcClient("stated", timeout=5.0)
            except Exception as exc:
                logger.warning(f"Failed to initialize audit client: {exc}")
                return
        
        audit_record = {
            "action": action,
            "session_id": session_id or "",
            "model_type": model_type,
            "peer_uid": peer.uid,
            "peer_gid": peer.gid,
            "result": result,
            "execution_time_ms": execution_time_ms,
            **extra
        }
        
        try:
            self._audit_client.call("audit.append", audit_record)
            logger.debug(f"Audit logged: {action}")
        except Exception as exc:
            logger.warning(f"Failed to log audit: {exc}")
    
    def execute_model(self, params: dict, peer: PeerCredentials) -> dict:
        """Execute a model request with full validation and audit logging."""
        start_time = time.monotonic()
        
        # Validate request
        self._validate_request_size(params)
        
        # Extract parameters
        model_type = params.get("model_type")
        if not model_type or not isinstance(model_type, str):
            raise JsonRpcError(
                INVALID_PARAMS,
                "model_type is required",
                {"user_message": "Modeltypen skal angives"}
            )
        
        session_id = params.get("session_id")
        
        # Get worker
        try:
            worker = self.get_worker(model_type)
        except ValueError as exc:
            raise JsonRpcError(
                INVALID_PARAMS,
                str(exc),
                {"user_message": f"Ukendt modeltype: {model_type}"}
            )
        
        # Execute with timeout
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(worker.execute, params, peer)
                try:
                    result = future.result(timeout=REQUEST_TIMEOUT)
                    execution_time_ms = (time.monotonic() - start_time) * 1000
                    
                    # Log success
                    self._log_audit(
                        action="model.execute",
                        session_id=session_id,
                        model_type=model_type,
                        peer=peer,
                        result="success",
                        execution_time_ms=execution_time_ms,
                        input_hash=params.get("_input_hash", ""),
                        output_hash=result.get("_output_hash", "")
                    )
                    
                    return result
                except concurrent.futures.TimeoutError:
                    future.cancel()
                    execution_time_ms = (time.monotonic() - start_time) * 1000
                    
                    # Log timeout
                    self._log_audit(
                        action="model.execute",
                        session_id=session_id,
                        model_type=model_type,
                        peer=peer,
                        result="timeout",
                        execution_time_ms=execution_time_ms
                    )
                    
                    raise JsonRpcError(
                        INTERNAL_ERROR,
                        f"Request timed out after {REQUEST_TIMEOUT} seconds",
                        {"user_message": f"Anmodningen timeoutede efter {REQUEST_TIMEOUT} sekunder"}
                    )
        except ModelWorkerError as exc:
            execution_time_ms = (time.monotonic() - start_time) * 1000
            
            # Log failure
            self._log_audit(
                action="model.execute",
                session_id=session_id,
                model_type=model_type,
                peer=peer,
                result="error",
                execution_time_ms=execution_time_ms,
                error=str(exc)
            )
            
            raise JsonRpcError(
                INTERNAL_ERROR,
                str(exc),
                {"user_message": f"Modeludførelse fejlede: {exc}"}
            )


class ModelWorker:
    """Base class for model workers.
    
    Each worker type (script, mistral, veritas) should inherit from this
    and implement the _execute method.
    """
    
    def __init__(self, worker_type: str):
        self.worker_type = worker_type
        self._socket_path = str(run_dir() / f"model-{worker_type}.sock")
    
    def execute(self, params: dict, peer: PeerCredentials) -> dict:
        """Execute the model with the given parameters.
        
        This method should be overridden by subclasses.
        """
        raise NotImplementedError(f"Worker {self.worker_type} must implement execute()")
    
    def health(self) -> dict:
        """Health check for the worker."""
        return {
            "worker_type": self.worker_type,
            "status": "healthy",
            "socket_path": self._socket_path
        }


class ScriptWorker(ModelWorker):
    """Worker for executing user-provided Python scripts.
    
    Security: Runs in separate process with eira-model user isolation.
    """
    
    def __init__(self):
        super().__init__("script")
    
    def execute(self, params: dict, peer: PeerCredentials) -> dict:
        """Execute a Python script."""
        script_id = params.get("script_id")
        input_data = params.get("input", {})
        
        if not script_id or not isinstance(script_id, str):
            raise ModelWorkerError("script_id is required")
        
        # TODO: Implement actual script execution via subprocess
        # This will call the actual script worker process
        # For now, return a stub response
        logger.warning(f"ScriptWorker.execute: Script execution not yet implemented for {script_id}")
        
        return {
            "output": f"Script {script_id} executed with input: {input_data}",
            "script_id": script_id,
            "model_type": "script",
            "_output_hash": "stub"  # Will be replaced with actual hash
        }


class MistralWorker(ModelWorker):
    """Worker for executing Mistral AI models.
    
    Security: Runs in separate process with eira-model user isolation.
    Uses local Ollama server via Unix socket (no HTTP).
    """
    
    def __init__(self):
        super().__init__("mistral")
        self._ollama_socket = "/run/eira/ollama.sock"
    
    def execute(self, params: dict, peer: PeerCredentials) -> dict:
        """Execute a Mistral model request."""
        model_name = params.get("model_name", "mistral")
        prompt = params.get("prompt")
        
        if not prompt or not isinstance(prompt, str):
            raise ModelWorkerError("prompt is required")
        
        # TODO: Implement actual Mistral execution via Ollama Unix socket
        # For now, return a stub response
        logger.warning(f"MistralWorker.execute: Mistral execution not yet implemented for {model_name}")
        
        return {
            "output": f"Mistral {model_name} response to: {prompt[:50]}...",
            "model": model_name,
            "done": True,
            "model_type": "mistral",
            "_output_hash": "stub"  # Will be replaced with actual hash
        }


class VeritasWorker(ModelWorker):
    """Worker for Veritas evidence processing.
    
    Security: Runs in separate process with eira-model user isolation.
    """
    
    def __init__(self):
        super().__init__("veritas")
    
    def execute(self, params: dict, peer: PeerCredentials) -> dict:
        """Execute Veritas evidence processing."""
        evidence = params.get("evidence")
        
        if not evidence:
            raise ModelWorkerError("evidence is required")
        
        # TODO: Implement actual Veritas processing
        # For now, return a stub response
        logger.warning("VeritasWorker.execute: Veritas processing not yet implemented")
        
        return {
            "result": "evidence_processed",
            "evidence_hash": "stub",
            "model_type": "veritas",
            "_output_hash": "stub"  # Will be replaced with actual hash
        }


# Global gateway instance
_gateway = None
_gateway_lock = threading.Lock()


def get_gateway() -> ModelGateway:
    """Get or create the global gateway instance."""
    global _gateway
    if _gateway is None:
        with _gateway_lock:
            if _gateway is None:
                _gateway = ModelGateway()
                # Register default workers
                _gateway.register_worker("script", ScriptWorker())
                _gateway.register_worker("mistral", MistralWorker())
                _gateway.register_worker("veritas", VeritasWorker())
    return _gateway


def register_model_handlers(server: JsonRpcServer) -> None:
    """Register model handlers with a JSON-RPC server."""
    gateway = get_gateway()
    
    def model_execute(params: dict[str, Any]) -> dict[str, Any]:
        """Handle model.execute requests."""
        peer = params.pop(PEER_KEY, None)
        if peer is None:
            raise JsonRpcError(
                INVALID_REQUEST,
                "Peer credentials required",
                {"user_message": "Kredentialer kræves"}
            )
        
        # Convert peer dict to PeerCredentials
        try:
            peer_creds = PeerCredentials(
                pid=peer.get("pid", 0),
                uid=peer.get("uid", 0),
                gid=peer.get("gid", 0)
            )
        except (KeyError, TypeError) as exc:
            raise JsonRpcError(
                INVALID_REQUEST,
                f"Invalid peer credentials: {exc}",
                {"user_message": "Ugyldige kredentialer"}
            )
        
        # Validate peer
        gateway._validate_peer(peer_creds)
        
        # Execute model
        return gateway.execute_model(params, peer_creds)
    
    def model_list(params: dict[str, Any]) -> dict[str, Any]:
        """Handle model.list requests."""
        gateway = get_gateway()
        return {"workers": gateway.list_workers()}
    
    def model_health(params: dict[str, Any]) -> dict[str, Any]:
        """Handle model.health requests."""
        gateway = get_gateway()
        workers = gateway.list_workers()
        worker_health = {}
        for worker_type in workers:
            try:
                worker = gateway.get_worker(worker_type)
                worker_health[worker_type] = worker.health()
            except Exception as exc:
                worker_health[worker_type] = {"status": "error", "error": str(exc)}
        
        return {
            "daemon": "eira-modeld",
            "status": "healthy",
            "workers": worker_health
        }
    
    # Register handlers with peer credential requirement
    server.register("model.execute", model_execute)
    model_execute.wants_peer = True
    
    server.register("model.list", model_list)
    server.register("model.health", model_health)
    server.register("health", model_health)
