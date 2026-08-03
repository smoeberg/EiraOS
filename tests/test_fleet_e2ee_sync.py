import asyncio
import json
import socket
from websockets.asyncio.client import connect
from app.fleet.device_registry import DeviceRegistry
from app.fleet.e2ee import StatePayloadEncryptor
from app.fleet.merkle_sync import MerkleSyncEngine
from app.daemons.fleetd import FleetSyncService, FleetWebSocketServer, generate_device_keypair

def _services():
    device_a = generate_device_keypair("device-a", "Laptop")
    device_b = generate_device_keypair("device-b", "Phone")
    registry = DeviceRegistry()
    registry.register(device_b)
    tokens = {"device-b": registry.issue_auth_token("device-b")}
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
        websocket_server = FleetWebSocketServer(device_a, port=port)
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
