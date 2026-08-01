from __future__ import annotations

import asyncio
import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from websockets.asyncio.client import connect

from app.core.state import State
from app.core.store import StateStore
from app.daemons.fleetd import FleetSyncService, FleetWebSocketServer
from app.fleet.device_registry import DeviceAuthorizationError, DeviceRegistry
from app.fleet.e2ee import PayloadIntegrityError, StatePayloadEncryptor
from app.fleet.merkle_sync import MerkleSyncEngine


def _public_key() -> str:
    raw = X25519PrivateKey.generate().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def _pair(registry: DeviceRegistry, device_id: str, os_type: str) -> tuple[str, str]:
    public_key = _public_key()
    token = registry.create_pairing_token()
    enrollment = registry.enroll(
        pairing_code=token["code"],
        device_id=device_id,
        name=device_id,
        os_type=os_type,
        public_key=public_key,
    )
    return public_key, enrollment.auth_token


def _services() -> tuple[
    FleetSyncService, FleetSyncService, DeviceRegistry, dict[str, str]
]:
    registry = DeviceRegistry()
    _, token_a = _pair(registry, "device-a", "Ubuntu")
    _, token_b = _pair(registry, "device-b", "Android")
    master_key = bytes(range(32))
    fleet_salt = bytes(range(16))
    return (
        FleetSyncService(
            registry=registry,
            store=StateStore(),
            encryptor=StatePayloadEncryptor(master_key, fleet_salt=fleet_salt),
        ),
        FleetSyncService(
            registry=registry,
            store=StateStore(),
            encryptor=StatePayloadEncryptor(master_key, fleet_salt=fleet_salt),
        ),
        registry,
        {"device-a": token_a, "device-b": token_b},
    )


def _transfer(
    source: FleetSyncService,
    target: FleetSyncService,
    *,
    requester_id: str,
    sender_id: str,
    requester_token: str,
    sender_token: str,
) -> dict:
    handshake = source.handshake(
        {
            "device_id": requester_id,
            "auth_token": requester_token,
            "headers": target.headers(),
        }
    )
    response = source.request_blocks(
        {
            "device_id": requester_id,
            "auth_token": requester_token,
            "hashes": handshake["offer_hashes"],
        }
    )
    return target.push_blocks(
        {
            "device_id": sender_id,
            "auth_token": sender_token,
            "blocks": response["blocks"],
        }
    )


def test_e2ee_state_sync_between_two_devices() -> None:
    device_a, device_b, _, tokens = _services()
    previous = None
    for version in range(1, 6):
        state = State(
            type="DocumentState",
            version=version,
            previous_state_id=previous.id if previous else None,
            payload={"version": version, "secret": f"classified-{version}"},
        )
        device_a.store.append(state)
        previous = state

    result = _transfer(
        device_a,
        device_b,
        requester_id="device-b",
        sender_id="device-a",
        requester_token=tokens["device-b"],
        sender_token=tokens["device-a"],
    )

    assert result == {
        "accepted": 5,
        "skipped": 0,
        "invalid": 0,
        "root": MerkleSyncEngine().snapshot(device_a.store.list_states()).root,
    }
    assert [state.hash for state in device_b.store.list_states()] == [
        state.hash for state in device_a.store.list_states()
    ]


def test_unauthorized_device_rejected() -> None:
    device_a, _, _, _ = _services()
    with pytest.raises(DeviceAuthorizationError, match="not paired"):
        device_a.handshake({"device_id": "intruder", "headers": []})
    with pytest.raises(DeviceAuthorizationError, match="token is invalid"):
        device_a.handshake(
            {
                "device_id": "device-b",
                "auth_token": "stolen-token",
                "headers": [],
            }
        )


def test_reconciliation_after_offline_edits() -> None:
    device_a, device_b, _, tokens = _services()
    base = State(type="DocumentState", payload={"title": "shared"})
    device_a.store.append(base)
    device_b.store.append(base)
    branch_a = State(
        type="DocumentState",
        version=2,
        previous_state_id=base.id,
        payload={"edit": "offline-a"},
    )
    branch_b = State(
        type="DocumentState",
        version=2,
        previous_state_id=base.id,
        payload={"edit": "offline-b"},
    )
    device_a.store.append(branch_a)
    device_b.store.append(branch_b)

    result_b = _transfer(
        device_a,
        device_b,
        requester_id="device-b",
        sender_id="device-a",
        requester_token=tokens["device-b"],
        sender_token=tokens["device-a"],
    )
    result_a = _transfer(
        device_b,
        device_a,
        requester_id="device-a",
        sender_id="device-b",
        requester_token=tokens["device-a"],
        sender_token=tokens["device-b"],
    )

    assert result_a["accepted"] == 1
    assert result_b["accepted"] == 1
    assert {state.hash for state in device_a.store.list_states()} == {
        state.hash for state in device_b.store.list_states()
    }
    snapshot_a = device_a.merkle.snapshot(device_a.store.list_states())
    snapshot_b = device_b.merkle.snapshot(device_b.store.list_states())
    assert snapshot_a.root == snapshot_b.root
    assert set(snapshot_a.heads) == {str(branch_a.id), str(branch_b.id)}


def test_wrong_e2ee_key_and_metadata_tampering_are_rejected() -> None:
    state = State(type="SecretState", payload={"secret": "not plaintext"})
    sender = StatePayloadEncryptor(bytes(range(32)), fleet_salt=bytes(range(16)))
    wrong_receiver = StatePayloadEncryptor(
        bytes(reversed(range(32))), fleet_salt=bytes(range(16))
    )
    envelope = sender.encrypt_state(state)
    assert "not plaintext" not in json.dumps(envelope)
    with pytest.raises(PayloadIntegrityError):
        wrong_receiver.decrypt_state(envelope)

    envelope["metadata"]["version"] = 99
    with pytest.raises(PayloadIntegrityError):
        sender.decrypt_state(envelope)


def test_revoked_device_cannot_sync() -> None:
    device_a, _, registry, tokens = _services()
    registry.revoke("device-b")
    with pytest.raises(DeviceAuthorizationError, match="revoked"):
        device_a.handshake(
            {
                "device_id": "device-b",
                "auth_token": tokens["device-b"],
                "headers": [],
            }
        )


def test_websocket_handshake_uses_the_same_authorization_boundary() -> None:
    async def scenario() -> None:
        device_a, _, registry, tokens = _services()
        public_key = registry.get("device-b").public_key
        websocket_server = FleetWebSocketServer(device_a, port=0)
        await websocket_server.start()
        try:
            async with connect(
                f"ws://127.0.0.1:{websocket_server.port}"
            ) as websocket:
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
