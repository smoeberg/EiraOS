"""Regression: a fleet client must not be able to skip the signature by itself.

Before the fix, ``FleetSyncService._authorize`` read ``_session_authenticated``
from caller-supplied params. Any IPC or WebSocket client could send
``{"device_id": "<paired id>", "_session_authenticated": true}`` and pass the
handshake without proof. Since F1c.1 the proof is a signed challenge.
"""

from __future__ import annotations

import pytest

from app.core.store import StateStore
from app.daemons.fleetd import FleetSyncService
from app.fleet.device_registry import DeviceAuthorizationError, DeviceRegistry
from app.fleet.e2ee import StatePayloadEncryptor
from tests.fleet_device import FleetTestDevice

DEVICE = FleetTestDevice("Victim")
DEVICE_ID = DEVICE.device_id


@pytest.fixture
def paired(tmp_path):
    registry = DeviceRegistry(str(tmp_path / "devices.db"))
    DEVICE.enroll(registry)
    service = FleetSyncService(
        registry=registry,
        store=StateStore(),
        encryptor=StatePayloadEncryptor(
            StatePayloadEncryptor.generate_master_key(),
            fleet_salt=StatePayloadEncryptor.generate_fleet_salt(),
        ),
    )
    return service, registry


SPOOFED = {"device_id": DEVICE_ID, "_session_authenticated": True}


@pytest.mark.parametrize("method", ["handshake", "request_blocks", "push_blocks"])
def test_direct_call_ignores_client_supplied_session_flag(paired, method):
    service, _ = paired
    with pytest.raises(DeviceAuthorizationError, match="signed challenge is required"):
        getattr(service, method)(dict(SPOOFED))


@pytest.mark.parametrize(
    "method", ["sync.handshake", "sync.request_blocks", "sync.push_blocks"]
)
def test_unauthenticated_websocket_message_cannot_spoof_session(paired, method):
    service, _ = paired
    with pytest.raises(DeviceAuthorizationError, match="signed challenge is required"):
        service.handle_message({"method": method, "params": dict(SPOOFED)})


def test_signed_handshake_still_succeeds(paired):
    service, registry = paired
    params = DEVICE.signed(registry, "sync.handshake", {"public_key": DEVICE.public_key})
    assert service.handshake(params)["accepted"] is True


def test_authenticated_websocket_session_needs_no_signature_per_message(paired):
    service, _ = paired
    method, result = service.handle_message(
        {"method": "sync.request_blocks", "params": {"hashes": []}},
        authenticated_device=DEVICE_ID,
    )
    assert method == "sync.request_blocks"
    assert result["count"] == 0
