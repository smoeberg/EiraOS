from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
import threading
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, serve

from app.core.store import StateStore
from app.database import get_connection, utc_now_iso
from app.fleet.device_registry import DeviceAuthorizationError, DeviceRegistry
from app.fleet.e2ee import PayloadIntegrityError, StatePayloadEncryptor
from app.fleet.merkle_sync import MerkleSyncEngine, StateHeader
from app.ipc.jsonrpc import JsonRpcError

FLEET_UNAUTHORIZED = -32030
FLEET_PROTOCOL_ERROR = -32031


class FleetProtocolError(ValueError):
    """Raised when a fleet synchronization message is invalid."""


class FleetSyncService:
    def __init__(
        self,
        *,
        registry: DeviceRegistry,
        store: StateStore,
        encryptor: StatePayloadEncryptor,
    ) -> None:
        self.registry = registry
        self.store = store
        self.encryptor = encryptor
        self.merkle = MerkleSyncEngine()

    def headers(self) -> list[dict[str, Any]]:
        return [
            StateHeader.from_value(state).as_dict() for state in self.store.list_states()
        ]

    def _authorize(self, params: Mapping[str, Any], *, public_key: bool = False) -> str:
        device_id = str(params.get("device_id", ""))
        session_authenticated = bool(params.get("_session_authenticated", False))
        self.registry.assert_authorized(
            device_id,
            public_key=(
                str(params.get("public_key"))
                if public_key and params.get("public_key")
                else None
            ),
            auth_token=(
                str(params.get("auth_token")) if params.get("auth_token") else None
            ),
            require_token=not session_authenticated,
        )
        return device_id

    def handshake(self, params: Mapping[str, Any]) -> dict[str, Any]:
        device_id = self._authorize(params, public_key=True)
        remote_headers = list(params.get("headers", []))
        local_states = self.store.list_states()
        diff = self.merkle.diff(local_states, remote_headers)
        self.registry.heartbeat(device_id)
        return {
            "accepted": True,
            "device_id": device_id,
            "root": diff.local_root,
            "headers": self.headers(),
            "request_hashes": list(diff.missing_from_local),
            "offer_hashes": list(diff.missing_from_remote),
        }

    def request_blocks(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._authorize(params)
        requested = [str(value) for value in params.get("hashes", [])]
        if len(requested) > 10_000:
            raise FleetProtocolError("Too many state hashes requested")
        blocks = []
        for state_hash in requested:
            state = self.store.get_by_hash(state_hash)
            if state is not None:
                blocks.append(self.encryptor.encrypt_state(state))
        return {"blocks": blocks, "count": len(blocks)}

    def push_blocks(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._authorize(params)
        raw_blocks = list(params.get("blocks", []))
        if len(raw_blocks) > 10_000:
            raise FleetProtocolError("Too many state blocks supplied")

        pending = []
        invalid = 0
        for block in raw_blocks:
            try:
                pending.append(self.encryptor.decrypt_state(block))
            except PayloadIntegrityError:
                invalid += 1

        accepted = 0
        skipped = 0
        while pending:
            progress = False
            for state in tuple(pending):
                current = self.store.get_by_hash(state.hash)
                if current is not None:
                    pending.remove(state)
                    skipped += 1
                    progress = True
                    continue
                same_id = self.store.get_by_id(state.id)
                if same_id is not None and same_id.hash != state.hash:
                    pending.remove(state)
                    invalid += 1
                    progress = True
                    continue
                if (
                    state.previous_state_id is not None
                    and self.store.get_by_id(state.previous_state_id) is None
                ):
                    continue
                self.store.append(state)
                pending.remove(state)
                accepted += 1
                progress = True
            if not progress:
                invalid += len(pending)
                break

        snapshot = self.merkle.snapshot(self.store.list_states())
        return {
            "accepted": accepted,
            "skipped": skipped,
            "invalid": invalid,
            "root": snapshot.root,
        }

    def handle_message(
        self, message: Mapping[str, Any], *, authenticated_device: str | None = None
    ) -> tuple[str, dict[str, Any]]:
        method = str(message.get("method") or message.get("type") or "")
        params = dict(message.get("params") or {})
        if authenticated_device:
            supplied_device = params.get("device_id")
            if supplied_device is not None and str(supplied_device) != authenticated_device:
                raise DeviceAuthorizationError("WebSocket device identity cannot change")
            params["device_id"] = authenticated_device
            params["_session_authenticated"] = True
        if method == "sync.handshake":
            return method, self.handshake(params)
        if method == "sync.request_blocks":
            return method, self.request_blocks(params)
        if method == "sync.push_blocks":
            return method, self.push_blocks(params)
        raise FleetProtocolError(f"Unknown fleet sync method: {method}")


class FleetWebSocketServer:
    def __init__(
        self,
        service: FleetSyncService,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> None:
        self.service = service
        self.host = host
        self.port = port
        self._server: Server | None = None
        self._connections: dict[ServerConnection, str] = {}

    async def start(self) -> None:
        if self._server is not None:
            return
        self._server = await serve(
            self._handler,
            self.host,
            self.port,
            max_size=16 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=20,
        )
        sockets = self._server.sockets
        if sockets:
            self.port = int(sockets[0].getsockname()[1])

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None
        self._connections.clear()

    async def _broadcast_change(
        self, *, root: str, source: ServerConnection
    ) -> None:
        payload = json.dumps(
            {"type": "sync.changed", "params": {"root": root}},
            separators=(",", ":"),
        )
        peers = [connection for connection in self._connections if connection != source]
        if peers:
            await asyncio.gather(
                *(connection.send(payload) for connection in peers),
                return_exceptions=True,
            )

    async def _handler(self, websocket: ServerConnection) -> None:
        authenticated_device: str | None = None
        try:
            async for raw_message in websocket:
                request_id: Any = None
                try:
                    if not isinstance(raw_message, str):
                        raise FleetProtocolError("Binary WebSocket frames are not supported")
                    message = json.loads(raw_message)
                    if not isinstance(message, dict):
                        raise FleetProtocolError("Fleet message must be a JSON object")
                    request_id = message.get("id")
                    method = str(message.get("method") or message.get("type") or "")
                    if authenticated_device is None and method != "sync.handshake":
                        raise DeviceAuthorizationError("Handshake is required")
                    method, result = self.service.handle_message(
                        message, authenticated_device=authenticated_device
                    )
                    if method == "sync.handshake":
                        authenticated_device = str(result["device_id"])
                        self._connections[websocket] = authenticated_device
                    await websocket.send(
                        json.dumps(
                            {
                                "id": request_id,
                                "type": f"{method}.result",
                                "result": result,
                            },
                            separators=(",", ":"),
                        )
                    )
                    if method == "sync.push_blocks" and result["accepted"]:
                        await self._broadcast_change(root=result["root"], source=websocket)
                except (DeviceAuthorizationError, FleetProtocolError) as exc:
                    await websocket.send(
                        json.dumps(
                            {
                                "id": request_id,
                                "error": {
                                    "code": FLEET_UNAUTHORIZED
                                    if isinstance(exc, DeviceAuthorizationError)
                                    else FLEET_PROTOCOL_ERROR,
                                    "message": str(exc),
                                },
                            },
                            separators=(",", ":"),
                        )
                    )
                    if isinstance(exc, DeviceAuthorizationError):
                        await websocket.close(code=1008, reason="fleet authorization failed")
                        return
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    await websocket.send(
                        json.dumps(
                            {
                                "id": request_id,
                                "error": {
                                    "code": FLEET_PROTOCOL_ERROR,
                                    "message": f"Invalid fleet message: {exc}",
                                },
                            },
                            separators=(",", ":"),
                        )
                    )
        finally:
            self._connections.pop(websocket, None)


class FleetWebSocketRuntime:
    def __init__(self, server: FleetWebSocketServer) -> None:
        self.server = server
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._error: BaseException | None = None

    def start(self, timeout: float = 5.0) -> None:
        if self._thread and self._thread.is_alive():
            return

        def run() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.server.start())
                self._ready.set()
                loop.run_forever()
            except BaseException as exc:
                self._error = exc
                self._ready.set()
            finally:
                loop.run_until_complete(self.server.stop())
                loop.close()

        self._ready.clear()
        self._error = None
        self._thread = threading.Thread(target=run, name="eira-fleet-ws", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout):
            raise TimeoutError("Timed out starting fleet WebSocket server")
        if self._error:
            raise RuntimeError("Failed to start fleet WebSocket server") from self._error

    def stop(self) -> None:
        loop = self._loop
        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.server.stop(), loop)
            future.result(timeout=5)
            loop.call_soon_threadsafe(loop.stop)
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(5)


def _secret_path(name: str) -> Path:
    configured = os.environ.get("EIRA_FLEET_KEY_DIR")
    if configured:
        root = Path(configured)
    elif os.access("/var/lib/eira", os.W_OK):
        root = Path("/var/lib/eira")
    else:
        root = Path("data")
    root.mkdir(parents=True, exist_ok=True)
    return root / name


def _load_or_create_secret(env_name: str, filename: str, length: int) -> bytes:
    configured = os.environ.get(env_name)
    if configured:
        value = base64.b64decode(configured, validate=True)
        if len(value) != length:
            raise ValueError(f"{env_name} must decode to {length} bytes")
        return value
    path = _secret_path(filename)
    try:
        value = path.read_bytes()
    except FileNotFoundError:
        value = secrets.token_bytes(length)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
    if len(value) != length:
        raise ValueError(f"Invalid secret length in {path}")
    return value


_DEFAULT_SERVICE: FleetSyncService | None = None


def default_sync_service() -> FleetSyncService:
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        master_key = _load_or_create_secret(
            "EIRA_FLEET_MASTER_KEY", "fleet_master.key", 32
        )
        fleet_salt = _load_or_create_secret("EIRA_FLEET_SALT", "fleet_salt", 16)
        _DEFAULT_SERVICE = FleetSyncService(
            registry=DeviceRegistry(
                os.environ.get(
                    "EIRA_DEVICE_REGISTRY_DB", str(_secret_path("devices.db"))
                )
            ),
            store=StateStore(os.environ.get("EIRA_STATE_DB", "eira_state.db")),
            encryptor=StatePayloadEncryptor(
                master_key, fleet_salt=fleet_salt
            ),
        )
    return _DEFAULT_SERVICE


def fleet_enroll(params: dict[str, Any]) -> dict[str, Any]:
    """Backwards-compatible administrative inventory enrollment."""
    device_id = params.get("device_id") or str(uuid.uuid4())
    hostname = params.get("hostname", "unknown")
    tenant_id = params.get("tenant_id", "default")
    now = utc_now_iso()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO devices
            (device_id, hostname, tenant_id, bundle_applied, bundle_pending,
             compliance_pct, last_heartbeat, enrolled_at, status)
            VALUES (?, ?, ?, NULL, NULL, 100, ?, ?, 'active')
            ON CONFLICT(device_id) DO UPDATE SET
              hostname = excluded.hostname,
              last_heartbeat = excluded.last_heartbeat,
              status = 'active'
            """,
            (device_id, hostname, tenant_id, now, now),
        )
    return {"device_id": device_id, "status": "enrolled", "enrolled_at": now}


def fleet_heartbeat(params: dict[str, Any]) -> dict[str, Any]:
    device_id = params.get("device_id")
    if not device_id:
        raise JsonRpcError(-32602, "device_id required")
    now = utc_now_iso()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT device_id FROM devices WHERE device_id = ?", (device_id,)
        ).fetchone()
        if not row:
            raise JsonRpcError(-32602, "device not enrolled", {"device_id": device_id})
        connection.execute(
            """
            UPDATE devices SET last_heartbeat = ?, bundle_applied = ?,
            compliance_pct = ?, status = 'active' WHERE device_id = ?
            """,
            (
                now,
                params.get("bundle_applied"),
                int(params.get("compliance_pct", 100)),
                device_id,
            ),
        )
    return {"device_id": device_id, "ack": True, "server_time": now, "commands": []}


def fleet_device_get(params: dict[str, Any]) -> dict[str, Any]:
    device_id = params.get("device_id")
    if not device_id:
        raise JsonRpcError(-32602, "device_id required")
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM devices WHERE device_id = ?", (device_id,)
        ).fetchone()
    if not row:
        raise JsonRpcError(-32602, "device not found")
    return dict(row)


def fleet_list(params: dict[str, Any]) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM devices ORDER BY last_heartbeat DESC LIMIT ?",
            (min(int(params.get("limit", 50)), 500),),
        ).fetchall()
    return [dict(row) for row in rows]


def _rpc_guard(function: Any) -> Any:
    def guarded(params: dict[str, Any]) -> Any:
        try:
            return function(params)
        except DeviceAuthorizationError as exc:
            raise JsonRpcError(FLEET_UNAUTHORIZED, str(exc)) from exc
        except (FleetProtocolError, PayloadIntegrityError, ValueError) as exc:
            raise JsonRpcError(FLEET_PROTOCOL_ERROR, str(exc)) from exc

    return guarded


def register_fleet_handlers(server: Any) -> None:
    service = default_sync_service()
    server.register("fleet.enroll", fleet_enroll)
    server.register("fleet.heartbeat", fleet_heartbeat)
    server.register("fleet.device.get", fleet_device_get)
    server.register("fleet.list", fleet_list)
    server.register(
        "fleet.pairing.create",
        _rpc_guard(
            lambda params: service.registry.create_pairing_token(
                int(params.get("ttl_seconds", 300))
            )
        ),
    )
    server.register(
        "fleet.device.enroll",
        _rpc_guard(lambda params: service.registry.enroll(**params).as_dict()),
    )
    server.register(
        "fleet.device.revoke",
        _rpc_guard(
            lambda params: service.registry.revoke(str(params["device_id"])).as_dict()
        ),
    )
    server.register("sync.handshake", _rpc_guard(service.handshake))
    server.register("sync.request_blocks", _rpc_guard(service.request_blocks))
    server.register("sync.push_blocks", _rpc_guard(service.push_blocks))
    server.register("health", lambda _: {"daemon": "eira-fleetd", "ok": True})

    if os.environ.get("EIRA_FLEET_WS_ENABLED", "0") == "1":
        runtime = FleetWebSocketRuntime(
            FleetWebSocketServer(
                service,
                host=os.environ.get("EIRA_FLEET_WS_HOST", "0.0.0.0"),
                port=int(os.environ.get("EIRA_FLEET_WS_PORT", "8765")),
            )
        )
        runtime.start()
        server.add_cleanup(runtime.stop)
