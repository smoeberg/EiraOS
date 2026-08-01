from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable
from typing import Any

from app.ipc.auth import strip_and_validate_ipc_auth
from app.ipc.jsonrpc import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    JsonRpcError,
    error_response,
    success_response,
)
from app.ipc.paths import ensure_run_dir
from app.ipc.socket_security import PeerCredentialError, validate_peer_credentials
from app.ipc.transport import bind_server

Handler = Callable[[dict[str, Any]], Any]


class JsonRpcServer:
    def __init__(self, name: str, daemon: str):
        self.name = name
        self.daemon = daemon
        self._handlers: dict[str, Handler] = {}
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._server: socket.socket | None = None
        self._cleanup: Callable[[], None] | None = None
        self._startup_error: BaseException | None = None
        self._connections: set[socket.socket] = set()
        self._connections_lock = threading.Lock()
        self._stop_callbacks: list[Callable[[], None]] = []

    def register(self, method: str, handler: Handler) -> None:
        self._handlers[method] = handler

    def add_cleanup(self, callback: Callable[[], None]) -> None:
        self._stop_callbacks.append(callback)

    def handle_line(self, line: str) -> str:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            return json.dumps(error_response(None, INVALID_PARAMS, "Invalid JSON"))

        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        if not method or method not in self._handlers:
            return json.dumps(
                error_response(req_id, METHOD_NOT_FOUND, f"Unknown method: {method}")
            )

        try:
            params = strip_and_validate_ipc_auth(dict(params))
            result = self._handlers[method](params)
            return json.dumps(success_response(req_id, result), default=str)
        except JsonRpcError as exc:
            return json.dumps(
                error_response(req_id, exc.code, exc.message, exc.data)
            )
        except Exception as exc:  # noqa: BLE001 - JSON-RPC boundary
            return json.dumps(error_response(req_id, INTERNAL_ERROR, str(exc)))

    def _serve_client(self, conn: socket.socket) -> None:
        try:
            validate_peer_credentials(conn)
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
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if not line.strip():
                            continue
                        response = self.handle_line(line.decode("utf-8"))
                        conn.sendall((response + "\n").encode("utf-8"))
        except (PeerCredentialError, OSError):
            conn.close()
        finally:
            with self._connections_lock:
                self._connections.discard(conn)

    def _run(self) -> None:
        cleanup: Callable[[], None] | None = None
        try:
            ensure_run_dir()
            server, cleanup = bind_server(self.daemon)
            self._server = server
            self._cleanup = cleanup
            server.listen(8)
            server.settimeout(0.5)
            self._ready.set()
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
        except BaseException as exc:  # surfaced synchronously by start()
            self._startup_error = exc
            self._ready.set()
        finally:
            self._server = None
            if cleanup:
                cleanup()

    def start(self, timeout: float = 5.0) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._ready.clear()
        self._startup_error = None
        self._thread = threading.Thread(
            target=self._run, name=self.name, daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout):
            self.stop()
            raise TimeoutError(f"Timed out starting {self.name}")
        if self._startup_error:
            error = self._startup_error
            self.stop()
            raise RuntimeError(f"Failed to start {self.name}") from error

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        server = self._server
        if server:
            try:
                server.close()
            except OSError:
                pass

        with self._connections_lock:
            connections = tuple(self._connections)
        for conn in connections:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()

        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout)
        if self._cleanup:
            self._cleanup()
            self._cleanup = None
        while self._stop_callbacks:
            callback = self._stop_callbacks.pop()
            callback()


UnixJsonRpcServer = JsonRpcServer
