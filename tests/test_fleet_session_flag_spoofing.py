"""Regression: a fleet client must not be able to skip token auth by itself.

Before the fix, ``FleetSyncService._authorize`` read ``_session_authenticated``
from caller-supplied params. Any IPC or WebSocket client could send
``{"device_id": "<paired id>", "_session_authenticated": true}`` and pass the
handshake without an auth token and without the device public key.
"""

from __future__ import annotations

import base64
import os

import pytest

from app.core.store import StateStore
from app.daemons.fleetd import FleetSyncService
from app.fleet.device_registry import DeviceAuthorizationError, DeviceRegistry
from app.fleet.e2ee import StatePayloadEncryptor

DEVICE_ID = "victim-laptop"


@pytest.fixture
def paired(tmp_path):
    registry = DeviceRegistry(str(tmp_path / "devices.db"))
    pairing = registry.create_pairing_token(300)
    code = pairing.get("pairing_code") or pairing.get("code")
    public_key = base64.b64encode(os.urandom(32)).decode("ascii")
    enrollment = registry.enroll(
        pairing_code=code,
        device_id=DEVICE_ID,
        name="Victim",
        os_type="ubuntu",
        public_key=public_key,
    )
    service = FleetSyncService(
        registry=registry,
        store=StateStore(),
        encryptor=StatePayloadEncryptor(
            StatePayloadEncryptor.generate_master_key(),
            fleet_salt=StatePayloadEncryptor.generate_fleet_salt(),
        ),
    )
    return service, enrollment.as_dict(), public_key


SPOOFED = {"device_id": DEVICE_ID, "_session_authenticated": True}


@pytest.mark.parametrize("method", ["handshake", "request_blocks", "push_blocks"])
def test_direct_call_ignores_client_supplied_session_flag(paired, method):
    service, _, _ = paired
    with pytest.raises(DeviceAuthorizationError, match="token is required"):
        getattr(service, method)(dict(SPOOFED))


@pytest.mark.parametrize(
    "method", ["sync.handshake", "sync.request_blocks", "sync.push_blocks"]
)
def test_unauthenticated_websocket_message_cannot_spoof_session(paired, method):
    service, _, _ = paired
    with pytest.raises(DeviceAuthorizationError, match="token is required"):
        service.handle_message({"method": method, "params": dict(SPOOFED)})


def test_token_handshake_still_succeeds(paired):
    service, enrollment, public_key = paired
    token = enrollment.get("auth_token")
    assert token, "enrollment must return an auth token"
    result = service.handshake(
        {"device_id": DEVICE_ID, "public_key": public_key, "auth_token": token}
    )
    assert result["accepted"] is True


def test_authenticated_websocket_session_needs_no_token_per_message(paired):
    service, _, _ = paired
    method, result = service.handle_message(
        {"method": "sync.request_blocks", "params": {"hashes": []}},
        authenticated_device=DEVICE_ID,
    )
    assert method == "sync.request_blocks"
    assert result["count"] == 0
