from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, serve

from app.core.remote_store import RpcStateStore
from app.core.store import StateStore
from app.database import utc_now_iso
from app.fleet.device_registry import (
    DeviceAuthorizationError,
    DeviceRegistry,
    device_fingerprint,
)
from app.fleet.e2ee import PayloadIntegrityError, ReplayDetectedError, StatePayloadEncryptor
from app.fleet.merkle_sync import MerkleSyncEngine, StateHeader
from app.ipc.access import caller, read, signed
from app.ipc.auth import PEER_KEY
from app.ipc.jsonrpc import JsonRpcError
from app.ipc.socket_security import resolve_group_gid

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

    def _authorize(
        self,
        params: Mapping[str, Any],
        *,
        public_key: bool = False,
        session_authenticated: bool = False,
    ) -> str:
        # ``session_authenticated`` is an in-process flag set only by the
        # WebSocket handler after a token-verified handshake. It must never be
        # read from caller-supplied params, or any client could skip the token.
        device_id = str(params.get("device_id", ""))
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

    def handshake(
        self, params: Mapping[str, Any], *, session_authenticated: bool = False
    ) -> dict[str, Any]:
        device_id = self._authorize(
            params, public_key=True, session_authenticated=session_authenticated
        )
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

    def request_blocks(
        self, params: Mapping[str, Any], *, session_authenticated: bool = False
    ) -> dict[str, Any]:
        self._authorize(params, session_authenticated=session_authenticated)
        requested = [str(value) for value in params.get("hashes", [])]
        if len(requested) > 10_000:
            raise FleetProtocolError("Too many state hashes requested")
        blocks = []
        for state_hash in requested:
            state = self.store.get_by_hash(state_hash)
            if state is not None:
                blocks.append(self.encryptor.encrypt_state(state))
        return {"blocks": blocks, "count": len(blocks)}

    def push_blocks(
        self, params: Mapping[str, Any], *, session_authenticated: bool = False
    ) -> dict[str, Any]:
        self._authorize(params, session_authenticated=session_authenticated)
        raw_blocks = list(params.get("blocks", []))
        if len(raw_blocks) > 10_000:
            raise FleetProtocolError("Too many state blocks supplied")

        pending = []
        invalid = 0
        replays = 0
        for block in raw_blocks:
            try:
                pending.append(self.encryptor.decrypt_state(block))
            except ReplayDetectedError:
                replays += 1
            except PayloadIntegrityError:
                invalid += 1

        # Reject the entire batch before any write if envelope validation fails.
        if invalid:
            snapshot = self.merkle.snapshot(self.store.list_states())
            return {
                "accepted": 0,
                "skipped": replays,
                "invalid": invalid,
                "root": snapshot.root,
            }

        existing_states = self.store.list_states()
        existing_by_id = {state.id: state for state in existing_states}
        existing_hashes = {state.hash for state in existing_states}
        batch_by_id = {}
        candidates = []
        skipped = 0
        for state in pending:
            if state.hash in existing_hashes:
                skipped += 1
                continue
            previous = batch_by_id.get(state.id)
            if previous is not None:
                if previous.hash != state.hash:
                    invalid += 1
                    break
                skipped += 1
                continue
            existing = existing_by_id.get(state.id)
            if existing is not None and existing.hash != state.hash:
                invalid += 1
                break
            batch_by_id[state.id] = state
            candidates.append(state)

        ordered = []
        available_ids = set(existing_by_id)
        unresolved = list(candidates)
        while unresolved and not invalid:
            progressed = False
            for state in tuple(unresolved):
                parent_id = state.previous_state_id
                if parent_id is not None and parent_id not in available_ids:
                    continue
                ordered.append(state)
                available_ids.add(state.id)
                unresolved.remove(state)
                progressed = True
            if not progressed:
                invalid += len(unresolved)
                break

        if invalid:
            snapshot = self.merkle.snapshot(existing_states)
            return {
                "accepted": 0,
                "skipped": 0,
                "invalid": invalid,
                "root": snapshot.root,
            }

        for state in ordered:
            self.store.append(state)
        snapshot = self.merkle.snapshot(self.store.list_states())
        return {
            "accepted": len(ordered),
            "skipped": skipped + replays,
            "invalid": 0,
            "root": snapshot.root,
        }

    def handle_message(
        self, message: Mapping[str, Any], *, authenticated_device: str | None = None
    ) -> tuple[str, dict[str, Any]]:
        method = str(message.get("method") or message.get("type") or "")
        params = dict(message.get("params") or {})
        session_authenticated = False
        if authenticated_device:
            supplied_device = params.get("device_id")
            if supplied_device is not None and str(supplied_device) != authenticated_device:
                raise DeviceAuthorizationError("WebSocket device identity cannot change")
            params["device_id"] = authenticated_device
            session_authenticated = True
        if method == "sync.handshake":
            return method, self.handshake(
                params, session_authenticated=session_authenticated
            )
        if method == "sync.request_blocks":
            return method, self.request_blocks(
                params, session_authenticated=session_authenticated
            )
        if method == "sync.push_blocks":
            return method, self.push_blocks(
                params, session_authenticated=session_authenticated
            )
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
            store=RpcStateStore(),  # type: ignore[arg-type]
            encryptor=StatePayloadEncryptor(
                master_key, fleet_salt=fleet_salt
            ),
        )
    return _DEFAULT_SERVICE


FLEET_ADMIN_GROUP = "eira-fleet-admin"


def _require_fleet_admin(function: Any) -> Any:
    """Allow only root and members of ``eira-fleet-admin`` (from SO_PEERCRED).

    Creating pairing codes and revoking devices decides which devices are in
    the fleet. Membership of eira-clients (every desktop user and the model)
    is not enough. Fails closed if the group does not exist or the caller is
    unknown.
    """

    def guarded(params: dict[str, Any]) -> Any:
        peer = params.pop(PEER_KEY, None)
        if not _is_fleet_admin(peer):
            raise JsonRpcError(FLEET_UNAUTHORIZED, "fleet administrator required")
        return function(params)

    guarded.wants_peer = True  # type: ignore[attr-defined]
    return guarded


def _is_fleet_admin(peer: Any) -> bool:
    if peer is None or getattr(peer, "uid", None) is None:
        return False
    if peer.uid == 0:
        return True
    gid = resolve_group_gid(FLEET_ADMIN_GROUP)
    if gid is None:
        return False
    groups = peer.groups if peer.groups is not None else frozenset()
    return gid == peer.gid or gid in groups


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
    # The legacy inventory methods (fleet.enroll, fleet.heartbeat,
    # fleet.device.get, fleet.list) are removed: they wrote an unauthenticated
    # second device table next to the registry. The registry is the only one.
    server.register(
        "fleet.pairing.create",
        caller(
            _require_fleet_admin(
                _rpc_guard(
                    lambda params: service.registry.create_pairing_token(
                        int(params.get("ttl_seconds", 300))
                    )
                )
            )
        ),
    )
    server.register(
        "fleet.device.enroll",
        # The pairing token and the device's key proof decide.
        signed(_rpc_guard(lambda params: service.registry.enroll(**params).as_dict())),
    )
    server.register(
        "fleet.device.revoke",
        caller(
            _require_fleet_admin(
                _rpc_guard(
                    lambda params: service.registry.revoke(str(params["device_id"])).as_dict()
                )
            )
        ),
    )
    # Each sync call is authorized by the device's signature (_authorize).
    server.register("sync.handshake", signed(_rpc_guard(service.handshake)))
    server.register("sync.request_blocks", signed(_rpc_guard(service.request_blocks)))
    server.register("sync.push_blocks", signed(_rpc_guard(service.push_blocks)))
    server.register("health", read(lambda _: {"daemon": "eira-fleetd", "ok": True}))

    if os.environ.get("EIRA_FLEET_WS_ENABLED", "0") == "1":
        runtime = FleetWebSocketRuntime(
            FleetWebSocketServer(
                service,
                host=os.environ.get("EIRA_FLEET_WS_HOST", "127.0.0.1"),
                port=int(os.environ.get("EIRA_FLEET_WS_PORT", "8765")),
            )
        )
        runtime.start()
        server.add_cleanup(runtime.stop)


def generate_device_keypair(name: str) -> Any:
    """A test device with a random key; its id is the key's fingerprint."""
    import base64
    import os

    from app.fleet.device_registry import PairedDevice
    pub = base64.b64encode(os.urandom(32)).decode()
    return PairedDevice(
        device_id=device_fingerprint(pub),
        name=name,
        public_key=pub,
        os_type="Ubuntu",
        status="paired",
        paired_at=utc_now_iso(),
        last_heartbeat=None,
    )
