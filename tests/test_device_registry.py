import time

import pytest

from app.fleet.device_registry import DeviceAuthorizationError, DeviceRegistry
from tests.fleet_device import FleetTestDevice


def test_enrollment_flow_and_hashed_pairing_code():
    registry = DeviceRegistry()
    device = FleetTestDevice(os_type="android")
    enrolled = device.enroll(registry, registry.create_pairing_token(ttl_seconds=30)["code"])
    assert enrolled.status == "active"
    assert enrolled.os_type == "android"
    assert enrolled.device_id == device.device_id
    assert enrolled.signing_key == device.signing_key
    assert "auth_token" not in enrolled.as_dict()  # no bearer token (F1c.1)
    assert registry.list_active()[0].device_id == enrolled.device_id


def test_pairing_code_cannot_be_reused():
    registry = DeviceRegistry()
    code = registry.create_pairing_token()["code"]
    FleetTestDevice("One").enroll(registry, code)
    with pytest.raises(DeviceAuthorizationError):
        FleetTestDevice("Two").enroll(registry, code)


def test_expired_pairing_code_is_rejected():
    registry = DeviceRegistry()
    code = registry.create_pairing_token(ttl_seconds=30)["code"]
    with registry._lock:
        conn = registry._connect()
        conn.execute("UPDATE pairing_codes SET expires_at = ?", (int(time.time()) - 1,))
        conn.commit()
    with pytest.raises(DeviceAuthorizationError):
        FleetTestDevice().enroll(registry, code)


def test_revoke_removes_device_from_active_queries():
    registry = DeviceRegistry()
    d1 = FleetTestDevice().enroll(registry).device_id
    assert registry.revoke(d1).status == "revoked"
    assert registry.list_active() == []
    with pytest.raises(DeviceAuthorizationError):
        registry.assert_authorized(d1)


def test_heartbeat_expiry_is_fail_closed():
    registry = DeviceRegistry(heartbeat_ttl_seconds=1)
    d1 = FleetTestDevice().enroll(registry).device_id
    registry.heartbeat(d1)
    time.sleep(1.1)
    assert registry.list_active() == []
    assert registry.get(d1).status == "expired"
    with pytest.raises(DeviceAuthorizationError):
        registry.assert_authorized(d1)


def test_invalid_keys_are_rejected():
    registry = DeviceRegistry()
    code = registry.create_pairing_token()["code"]
    for field in ("public_key", "signing_key"):
        request = FleetTestDevice().enrollment(code) | {field: "not-a-key"}
        with pytest.raises(ValueError):
            registry.enroll(**request)


def test_pairing_code_is_hashed_at_rest():
    registry = DeviceRegistry()
    pairing = registry.create_pairing_token()
    with registry._lock:
        conn = registry._connect()
        row = conn.execute("SELECT code_hash FROM pairing_codes").fetchone()
    assert row[0] != pairing["code"]
    assert len(row[0]) == 64


def test_os_type_is_normalized_and_invalid_os_rejected():
    registry = DeviceRegistry()
    assert FleetTestDevice(os_type="Ubuntu").enroll(registry).os_type == "ubuntu"
    with pytest.raises(ValueError):
        FleetTestDevice(os_type="ios").enroll(registry)
