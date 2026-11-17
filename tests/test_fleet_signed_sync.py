"""Fleet synchronization is signed over a single-use challenge (UDVIKLINGSPLAN
F1c.1, vurderingen G-1).

Before, every sync call carried a bearer token: whoever had it could call for
ever, and nothing tied a call to the device's key. Now the device enrolls an
Ed25519 key with a proof, asks for a challenge, and signs the method, its
id, the nonce and the parameters. The nonce is used up by the call.
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from app.core.store import StateStore
from app.daemons.fleetd import FleetSyncService
from app.fleet import device_registry
from app.fleet.device_registry import (
    MAX_OPEN_CHALLENGES,
    DeviceAuthorizationError,
    DeviceRegistry,
    sync_message,
)
from app.fleet.e2ee import StatePayloadEncryptor
from tests.fleet_device import FleetTestDevice


@pytest.fixture()
def world(tmp_path):
    registry = DeviceRegistry(str(tmp_path / "devices.db"))
    service = FleetSyncService(
        registry=registry,
        store=StateStore(":memory:"),
        encryptor=StatePayloadEncryptor(
            StatePayloadEncryptor.generate_master_key(),
            fleet_salt=StatePayloadEncryptor.generate_fleet_salt(),
        ),
    )
    phone = FleetTestDevice("Phone")
    phone.enroll(registry)
    return registry, service, phone


def _request(service, phone, registry, **kwargs):
    return service.request_blocks(phone.signed(registry, "sync.request_blocks", {"hashes": []}, **kwargs))


def test_a_signed_call_is_accepted(world):
    registry, service, phone = world
    assert _request(service, phone, registry)["count"] == 0
    handshake = phone.signed(registry, "sync.handshake", {"public_key": phone.public_key, "headers": []})
    assert service.handshake(handshake)["accepted"] is True


def test_a_challenge_is_used_once(world):
    registry, service, phone = world
    params = phone.signed(registry, "sync.request_blocks", {"hashes": []})
    service.request_blocks(dict(params))
    with pytest.raises(DeviceAuthorizationError, match="used or expired"):
        service.request_blocks(dict(params))


def test_an_expired_challenge_is_refused(world, monkeypatch):
    registry, service, phone = world
    nonce = registry.challenge(phone.device_id)["nonce"]
    later = time.time() + device_registry.CHALLENGE_TTL_SECONDS + 5
    monkeypatch.setattr(device_registry.time, "time", lambda: later)
    with pytest.raises(DeviceAuthorizationError, match="used or expired"):
        _request(service, phone, registry, nonce=nonce)


def test_a_made_up_nonce_is_refused(world):
    registry, service, phone = world
    with pytest.raises(DeviceAuthorizationError, match="used or expired"):
        _request(service, phone, registry, nonce="never-issued")


def test_another_devices_challenge_cannot_be_used(world):
    registry, service, phone = world
    laptop = FleetTestDevice("Laptop")
    laptop.enroll(registry)
    nonce = registry.challenge(laptop.device_id)["nonce"]
    with pytest.raises(DeviceAuthorizationError, match="used or expired"):
        _request(service, phone, registry, nonce=nonce)


def test_changed_parameters_are_refused(world):
    registry, service, phone = world
    params = phone.signed(registry, "sync.request_blocks", {"hashes": []})
    params["hashes"] = ["something-else"]
    with pytest.raises(DeviceAuthorizationError, match="Signature does not verify"):
        service.request_blocks(params)


def test_a_signature_for_another_method_is_refused(world):
    registry, service, phone = world
    params = phone.signed(registry, "sync.request_blocks", {"blocks": []})
    with pytest.raises(DeviceAuthorizationError, match="Signature does not verify"):
        service.push_blocks(params)


def test_a_signature_with_another_key_is_refused(world):
    registry, service, phone = world
    impostor = FleetTestDevice("Impostor")
    nonce = registry.challenge(phone.device_id)["nonce"]
    forged = {"hashes": [], "device_id": phone.device_id, "nonce": nonce,
              "signature": impostor.sign(sync_message("sync.request_blocks", phone.device_id, nonce,
                                                      {"hashes": []}))}
    with pytest.raises(DeviceAuthorizationError, match="Signature does not verify"):
        service.request_blocks(forged)


def test_a_bad_signature_does_not_use_up_the_challenge(world):
    """Anyone in eira-clients may ask for a device's challenge; seeing a nonce
    must not let them burn it with a wrong signature."""
    registry, service, phone = world
    nonce = registry.challenge(phone.device_id)["nonce"]
    forged = phone.signed(registry, "sync.request_blocks", {"hashes": []}, nonce=nonce)
    forged["signature"] = FleetTestDevice().sign(b"wrong")
    with pytest.raises(DeviceAuthorizationError, match="Signature does not verify"):
        service.request_blocks(forged)
    assert _request(service, phone, registry, nonce=nonce)["count"] == 0


@pytest.mark.parametrize("missing", ["nonce", "signature"])
def test_a_call_without_the_proof_is_refused(world, missing):
    registry, service, phone = world
    params = phone.signed(registry, "sync.request_blocks", {"hashes": []})
    del params[missing]
    with pytest.raises(DeviceAuthorizationError, match="signed challenge is required"):
        service.request_blocks(params)


def test_an_old_bearer_token_is_no_proof(world):
    registry, service, phone = world
    with pytest.raises(DeviceAuthorizationError, match="signed challenge is required"):
        service.request_blocks({"device_id": phone.device_id, "auth_token": "anything", "hashes": []})


def test_a_revoked_device_gets_no_challenge_and_cannot_call(world):
    registry, service, phone = world
    params = phone.signed(registry, "sync.request_blocks", {"hashes": []})
    registry.revoke(phone.device_id)
    with pytest.raises(DeviceAuthorizationError, match="revoked"):
        service.request_blocks(params)
    with pytest.raises(DeviceAuthorizationError, match="revoked"):
        registry.challenge(phone.device_id)


def test_an_unknown_device_gets_no_challenge(world):
    registry, _, _ = world
    with pytest.raises(DeviceAuthorizationError, match="not paired"):
        registry.challenge(FleetTestDevice().device_id)


def test_open_challenges_are_limited_per_device(world):
    registry, service, phone = world
    for _ in range(MAX_OPEN_CHALLENGES):
        registry.challenge(phone.device_id)
    with pytest.raises(DeviceAuthorizationError, match="Too many open challenges"):
        registry.challenge(phone.device_id)
    # Another device is not affected by the phone's.
    laptop = FleetTestDevice("Laptop")
    laptop.enroll(registry)
    registry.challenge(laptop.device_id)


def test_the_handshake_key_must_be_the_enrolled_one(world):
    registry, service, phone = world
    params = phone.signed(registry, "sync.handshake",
                          {"public_key": FleetTestDevice().public_key, "headers": []})
    with pytest.raises(DeviceAuthorizationError, match="public key does not match"):
        service.handshake(params)


def test_transport_fields_are_not_signed(world):
    """The IPC token (_eira) and the kernel's caller (_peer) are added or
    stripped by the transport, so they are not part of what is signed."""
    registry, service, phone = world
    params = phone.signed(registry, "sync.request_blocks", {"hashes": []})
    params["_peer"] = "set by the server"
    assert service.request_blocks(params)["count"] == 0


def test_a_device_enrolled_with_a_token_must_enroll_again(tmp_path):
    """A registry from before F1c.1: devices with a token and no signing key
    cannot synchronize, and the token hashes are forgotten."""
    path = tmp_path / "devices.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE fleet_devices (device_id TEXT PRIMARY KEY, name TEXT NOT NULL,
            os_type TEXT NOT NULL, public_key TEXT UNIQUE NOT NULL,
            auth_token_hash TEXT NOT NULL, status TEXT NOT NULL,
            paired_at TEXT NOT NULL, last_heartbeat TEXT);
    """)
    conn.execute("INSERT INTO fleet_devices VALUES ('old', 'Old', 'ubuntu', 'a2V5', 'abc123', "
                 "'active', datetime('now'), datetime('now'))")
    conn.commit()
    conn.close()
    registry = DeviceRegistry(str(path))
    assert registry.get("old").signing_key is None
    with pytest.raises(DeviceAuthorizationError, match="enroll it again"):
        registry.challenge("old")
    with pytest.raises(DeviceAuthorizationError, match="enroll it again"):
        registry.verify_request("sync.request_blocks", "old", {"nonce": "n", "signature": "s"})
    with sqlite3.connect(path) as check:
        assert check.execute("SELECT auth_token_hash FROM fleet_devices").fetchone() == ("",)
