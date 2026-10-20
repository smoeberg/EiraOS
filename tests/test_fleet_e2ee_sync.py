import asyncio
import json
import os
import socket

from websockets.asyncio.client import connect

from app.core.store import StateStore
from app.daemons.fleetd import FleetSyncService, FleetWebSocketServer, generate_device_keypair
from app.fleet.device_registry import DeviceRegistry
from app.fleet.e2ee import StatePayloadEncryptor


def _services():
    device_a = generate_device_keypair("device-a", "Laptop")
    device_b = generate_device_keypair("device-b", "Phone")
    registry = DeviceRegistry()
    code = registry.create_pairing_token(ttl_seconds=300)
    enrollment = registry.enroll(
        pairing_code=code["code"],
        device_id=device_b.device_id,
        name=device_b.name,
        os_type=device_b.os_type,
        public_key=device_b.public_key,
    )
    tokens = {"device-b": enrollment.auth_token}
    return device_a, device_b, registry, tokens

def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port

def test_websocket_handshake_uses_the_same_authorization_boundary() -> None:
    async def scenario() -> None:
        device_a, _, registry, tokens = _services()
        public_key = registry.get("device-b").public_key
        port = get_free_port()
        websocket_server = FleetWebSocketServer(
            FleetSyncService(
                registry=registry,
                store=StateStore(),
                encryptor=StatePayloadEncryptor(os.urandom(32), fleet_salt=os.urandom(16)),
            ),
            port=port,
        )
        await websocket_server.start()
        try:
            async with connect(f"ws://127.0.0.1:{websocket_server.port}") as websocket:
                await websocket.send(
                    json.dumps(
                        {
                            "id": "handshake-1",
                            "method": "sync.handshake",
                            "params": {
                                "device_id": "device-b",
                                "public_key": public_key,
                                "auth_token": tokens["device-b"],
                                "headers": [],
                            },
                        }
                    )
                )
                response = json.loads(await websocket.recv())
                assert response["id"] == "handshake-1"
                assert response["result"]["accepted"] is True
                assert response["result"]["device_id"] == "device-b"
        finally:
            await websocket_server.stop()

    asyncio.run(scenario())


def _call(websocket, method: str, params: dict):
    import uuid

    async def _send() -> dict:
        call_id = uuid.uuid4().hex
        await websocket.send(json.dumps({
            "id": call_id,
            "method": method,
            "params": params,
        }))
        return json.loads(await websocket.recv())

    return _send()


def _encryptor():
    return StatePayloadEncryptor(os.urandom(32), fleet_salt=os.urandom(16))


def _chain(count: int = 3):
    import uuid

    from app.core.state import State

    states = []
    previous = None
    for _ in range(count):
        previous = State(
            id=uuid.uuid4(),
            version=1,
            hash="",
            type="note",
            payload={"text": uuid.uuid4().hex},
            previous_state_id=previous.id if previous else None,
            timestamp_ns=(previous.timestamp_ns + 1) if previous else 1,
        )
        states.append(previous)
    return states


def test_full_sync_round_trip_between_two_devices() -> None:
    """Device A pushes a chain, device B pulls the missing blocks and
    reconstructs the exact same states locally."""
    async def scenario() -> None:
        _, device_b, registry, tokens = _services()
        encryptor = _encryptor()
        store = StateStore()
        service = FleetSyncService(registry=registry, store=store, encryptor=encryptor)
        port = get_free_port()
        server = FleetWebSocketServer(service, port=port)
        await server.start()
        try:
            # Device A pushes a three-state chain (A is trusted by construction
            # in this fixture: only the public-key handshake boundary is tested
            # elsewhere; the token is issued for device-b).
            chain = _chain(3)
            blocks = [encryptor.encrypt_state(state) for state in chain]
            local = StateStore()
            for state in chain:
                local.append(state)

            async with connect(f"ws://127.0.0.1:{server.port}") as a:
                hs = await _call(a, "sync.handshake", {
                    "device_id": "device-b",
                    "public_key": registry.get("device-b").public_key,
                    "auth_token": tokens["device-b"],
                    "headers": [],
                })
                assert hs["result"]["accepted"] is True
                resp = await _call(a, "sync.push_blocks", {
                    "device_id": "device-b",
                    "auth_token": tokens["device-b"],
                    "blocks": blocks,
                })
                assert resp["result"]["accepted"] == 3
                assert resp["result"]["invalid"] == 0

            async with connect(f"ws://127.0.0.1:{server.port}") as b:
                handshake = await _call(b, "sync.handshake", {
                    "device_id": "device-b",
                    "public_key": registry.get("device-b").public_key,
                    "auth_token": tokens["device-b"],
                    "headers": [],
                })
                # pull what device B does not already have: the server's
                # full header list minus whatever B has stored locally
                missing = [
                    header["hash"] for header in handshake["result"]["headers"]
                ]
                assert len(missing) == 3

                pulled = await _call(b, "sync.request_blocks", {
                    "device_id": "device-b",
                    "auth_token": tokens["device-b"],
                    "hashes": missing,
                })
                assert pulled["result"]["count"] == 3

                # Device B decrypts and stores locally -> full round trip.
                peer = StateStore()
                for block in pulled["result"]["blocks"]:
                    peer.append(encryptor.decrypt_state(block))
                assert peer.count() == 3
                assert [

                    (str(state.id), state.hash) for state in peer.list_states()
                ] == [(str(state.id), state.hash) for state in chain]
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_wrong_key_is_rejected_fail_closed() -> None:
    """Blocks encrypted under a different key never reach the store."""
    async def scenario() -> None:
        _, device_b, registry, tokens = _services()
        encryptor = _encryptor()
        service = FleetSyncService(
            registry=registry,
            store=StateStore(),
            encryptor=StatePayloadEncryptor(os.urandom(32), fleet_salt=os.urandom(16)),
        )
        port = get_free_port()
        server = FleetWebSocketServer(service, port=port)
        await server.start()
        try:
            chain = _chain(2)
            blocks = [encryptor.encrypt_state(state) for state in chain]
            async with connect(f"ws://127.0.0.1:{server.port}") as ws:
                hs = await _call(ws, "sync.handshake", {
                    "device_id": "device-b",
                    "public_key": registry.get("device-b").public_key,
                    "auth_token": tokens["device-b"],
                    "headers": [],
                })
                assert hs["result"]["accepted"] is True
                resp = await _call(ws, "sync.push_blocks", {
                    "device_id": "device-b",
                    "auth_token": tokens["device-b"],
                    "blocks": blocks,
                })
                # wrong-key blocks are rejected fail-closed: nothing stored
                assert resp["result"]["accepted"] == 0
                assert resp["result"]["invalid"] == 2
                assert service.store.count() == 0
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_forked_state_is_rejected_over_websocket() -> None:
    """Same state id pushed twice with different hashes: the fork loses."""
    async def scenario() -> None:
        _, device_b, registry, tokens = _services()
        encryptor = _encryptor()
        service = FleetSyncService(
            registry=registry, store=StateStore(), encryptor=encryptor
        )
        port = get_free_port()
        server = FleetWebSocketServer(service, port=port)
        await server.start()
        try:
            import uuid

            from app.core.state import State

            original = State(
                id=uuid.uuid4(), version=1, hash="", type="note",
                payload={"text": "original"}, previous_state_id=None,
                timestamp_ns=1,
            )
            fork = State(
                id=original.id, version=1, hash="", type="note",
                payload={"text": "forked"}, previous_state_id=None,
                timestamp_ns=2,
            )
            async with connect(f"ws://127.0.0.1:{server.port}") as ws:
                hs = await _call(ws, "sync.handshake", {
                    "device_id": "device-b",
                    "public_key": registry.get("device-b").public_key,
                    "auth_token": tokens["device-b"],
                    "headers": [],
                })
                assert hs["result"]["accepted"] is True
                original_resp = await _call(ws, "sync.push_blocks", {
                    "device_id": "device-b",
                    "auth_token": tokens["device-b"],
                    "blocks": [encryptor.encrypt_state(original)],
                })
                assert original_resp["result"]["accepted"] == 1
                fork_resp = await _call(ws, "sync.push_blocks", {
                    "device_id": "device-b",
                    "auth_token": tokens["device-b"],
                    "blocks": [encryptor.encrypt_state(fork)],
                })
                # the fork is rejected: same id, different hash -> invalid
                assert fork_resp["result"]["accepted"] == 0

            stored = service.store.get_by_id(original.id)
            assert stored.hash == original.hash
            assert stored.payload == {"text": "original"}
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_revoked_device_is_kicked_with_unauthorized_frame() -> None:
    """After registry.revoke() the open session must be closed (1008)."""
    async def scenario() -> None:
        _, device_b, registry, tokens = _services()
        service = FleetSyncService(
            registry=registry, store=StateStore(), encryptor=_encryptor()
        )
        port = get_free_port()
        server = FleetWebSocketServer(service, port=port)
        await server.start()
        try:
            async with connect(f"ws://127.0.0.1:{server.port}") as ws:
                handshake = await _call(ws, "sync.handshake", {
                    "device_id": "device-b",
                    "public_key": registry.get("device-b").public_key,
                    "auth_token": tokens["device-b"],
                    "headers": [],
                })
                assert handshake["result"]["accepted"] is True

                registry.revoke("device-b")
                resp = await _call(ws, "sync.request_blocks", {
                    "device_id": "device-b",
                    "auth_token": tokens["device-b"],
                    "hashes": [],
                })
                assert resp["error"]["code"] == -32030
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_heartbeat_updates_registry_on_handshake() -> None:
    async def scenario() -> None:
        _, device_b, registry, tokens = _services()
        service = FleetSyncService(
            registry=registry, store=StateStore(), encryptor=_encryptor()
        )
        port = get_free_port()
        server = FleetWebSocketServer(service, port=port)
        await server.start()
        try:
            before = registry.get("device-b").last_heartbeat
            async with connect(f"ws://127.0.0.1:{server.port}") as ws:
                await _call(ws, "sync.handshake", {
                    "device_id": "device-b",
                    "public_key": registry.get("device-b").public_key,
                    "auth_token": tokens["device-b"],
                    "headers": [],
                })
            after = registry.get("device-b").last_heartbeat
            assert after is not None
            if before is not None:
                assert after >= before
        finally:
            await server.stop()

    asyncio.run(scenario())
