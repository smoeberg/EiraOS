from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable
from typing import Any

from app.ipc.jsonrpc import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    JsonRpcError,
    error_response,
    success_response,
)
from app.ipc.auth import strip_and_validate_ipc_auth
from app.ipc.paths import ensure_run_dir
from app.ipc.transport import bind_server

Handler = Callable[[dict[str, Any]], Any]


class JsonRpcServer:
    def __init__(self, name: str, daemon: str):
        self.name = name
        self.daemon = daemon
        self._handlers: dict[str, Handler] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cleanup: Callable[[], None] | None = None

    def register(self, method: str, handler: Handler) -> None:
        self._handlers[method] = handler

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
        except Exception as exc:  # noqa: BLE001 — RPC boundary
            return json.dumps(error_response(req_id, INTERNAL_ERROR, str(exc)))

    def _serve_client(self, conn: socket.socket) -> None:
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

    def _run(self) -> None:
        ensure_run_dir()
        server, cleanup = bind_server(self.daemon)
        self._cleanup = cleanup
        with server:
            server.listen(8)
            server.settimeout(0.5)
            while not self._stop.is_set():
                try:
                    conn, _ = server.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                threading.Thread(
                    target=self._serve_client,
                    args=(conn,),
                    daemon=True,
                ).start()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._cleanup:
            self._cleanup()
            self._cleanup = None


# Backwards compatibility
UnixJsonRpcServer = JsonRpcServer
