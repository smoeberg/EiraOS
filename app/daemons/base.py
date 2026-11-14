from __future__ import annotations

import json
import logging
import socket
import threading
from collections.abc import Callable
from typing import Any

from app.ipc.access import (
    ACCESS_DENIED,
    Access,
    access_of,
    callers_of,
    daemon_write_allowed,
    peer_daemon,
    service_uid,
)
from app.ipc.auth import PEER_KEY, strip_and_validate_ipc_auth
from app.ipc.jsonrpc import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    JsonRpcError,
    error_response,
    success_response,
)
from app.ipc.paths import ensure_run_dir
from app.ipc.socket_security import PeerCredentialError, validate_peer_credentials
from app.ipc.transport import bind_server

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Any]
MAX_REQUEST_BYTES = 4 * 1024 * 1024


class JsonRpcServer:
    def __init__(self, name: str, daemon: str):
        self.name = name
        self.daemon = daemon
        self._handlers: dict[str, Handler] = {}
        self._access: dict[str, Access] = {}
        # Methods that receive the caller (SO_PEERCRED) as params["_peer"].
        self._peer_methods: set[str] = set()
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
        kind = access_of(handler)
        if kind is None:
            # app/ipc/access.py: no method without an access class (F0b).
            raise ValueError(f"{self.daemon}: method {method!r} has no access class")
        self._handlers[method] = handler
        self._access[method] = kind
        if getattr(handler, "wants_peer", False):
            self._peer_methods.add(method)
        else:
            self._peer_methods.discard(method)

    def access_classes(self) -> dict[str, Access]:
        return dict(self._access)

    def add_cleanup(self, callback: Callable[[], None]) -> None:
        self._stop_callbacks.append(callback)

    @staticmethod
    def _valid_request_id(value: Any) -> bool:
        return isinstance(value, (str, int, float)) and not isinstance(value, bool)

    def handle_line(self, line: str, peer: Any = None) -> str:
        if len(line.encode("utf-8")) > MAX_REQUEST_BYTES:
            return json.dumps(error_response(None, INVALID_PARAMS, "Request too large"))
        try:
            request = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return json.dumps(error_response(None, INVALID_REQUEST, "Invalid JSON"))

        if not isinstance(request, dict):
            return json.dumps(
                error_response(None, INVALID_REQUEST, "Request must be a JSON object")
            )

        req_id = request.get("id")
        if request.get("jsonrpc") != "2.0":
            return json.dumps(
                error_response(
                    req_id if self._valid_request_id(req_id) else None,
                    INVALID_REQUEST,
                    'jsonrpc must be "2.0"',
                )
            )
        if "id" not in request or not self._valid_request_id(req_id):
            return json.dumps(
                error_response(None, INVALID_REQUEST, "Request id must be a string or number")
            )

        method = request.get("method")
        if not isinstance(method, str) or not method:
            return json.dumps(
                error_response(req_id, INVALID_REQUEST, "method must be a non-empty string")
            )
        params = request.get("params", {})
        if not isinstance(params, dict):
            return json.dumps(
                error_response(req_id, INVALID_PARAMS, "params must be an object")
            )
        if method not in self._handlers:
            return json.dumps(
                error_response(req_id, METHOD_NOT_FOUND, f"Unknown method: {method}")
            )

        try:
            params = strip_and_validate_ipc_auth(dict(params))
            # The caller comes from the kernel (SO_PEERCRED), never from the
            # request: a client-supplied "_peer" is dropped (bilag A pkt. 1).
            params.pop(PEER_KEY, None)
            if self._access[method] is Access.DAEMON_WRITE and not daemon_write_allowed(
                peer, callers_of(self._handlers[method])
            ):
                if getattr(peer, "uid", None) == service_uid():
                    # The service user, but not a named caller: worth a line in
                    # the journal (which daemon the kernel said it was).
                    logger.warning(
                        "%s: daemon_write %s refused for pid %s (label %r, daemon %r)",
                        self.daemon, method, getattr(peer, "pid", None),
                        getattr(peer, "label", None), peer_daemon(peer),
                    )
                raise JsonRpcError(
                    ACCESS_DENIED,
                    "E_ACCESS_DAEMON_ONLY",
                    {"user_message": "Kun EiraOS' egne tjenester må skrive her."},
                )
            if method in self._peer_methods:
                params[PEER_KEY] = peer
            result = self._handlers[method](params)
            return json.dumps(success_response(req_id, result), default=str)
        except JsonRpcError as exc:
            return json.dumps(error_response(req_id, exc.code, exc.message, exc.data))
        except Exception:  # noqa: BLE001 - JSON-RPC boundary
            return json.dumps(
                error_response(req_id, INTERNAL_ERROR, "Internal daemon error")
            )

    def _serve_client(self, conn: socket.socket) -> None:
        try:
            peer = validate_peer_credentials(conn)
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
                            (
                                json.dumps(
                                    error_response(
                                        None, INVALID_PARAMS, "Request too large"
                                    )
                                )
                                + "\n"
                            ).encode("utf-8")
                        )
                        return
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if not line.strip():
                            continue
                        response = self.handle_line(line.decode("utf-8"), peer)
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
