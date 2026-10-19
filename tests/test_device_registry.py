import base64
import sqlite3
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from app.fleet.device_registry import DeviceAuthorizationError, DeviceRegistry


def public_key() -> str:
    key = X25519PrivateKey.generate().public_key().public_bytes_raw()
    return base64.b64encode(key).decode("ascii")


def test_enrollment_flow_and_hashed_pairing_code():
    registry = DeviceRegistry()
    pairing = registry.create_pairing_token(ttl_seconds=30)
    enrolled = registry.enroll(pairing_code=pairing["code"], device_id="d1", name="Phone", os_type="android", public_key=public_key())
    assert enrolled.device.status == "active"
    assert enrolled.device.os_type == "android"
    assert enrolled.auth_token
    connection = sqlite3.connect(":memory:")
    assert pairing["code"] not in str(pairing)
    assert registry.list_active()[0].device_id == "d1"


def test_pairing_code_cannot_be_reused():
    registry = DeviceRegistry()
    code = registry.create_pairing_token()["code"]
    registry.enroll(pairing_code=code, device_id="d1", name="One", os_type="ubuntu", public_key=public_key())
    with pytest.raises(DeviceAuthorizationError):
        registry.enroll(pairing_code=code, device_id="d2", name="Two", os_type="ubuntu", public_key=public_key())


def test_expired_pairing_code_is_rejected():
    registry = DeviceRegistry()
    code = registry.create_pairing_token(ttl_seconds=30)["code"]
    with registry._lock:
        conn = registry._connect()
        conn.execute("UPDATE pairing_codes SET expires_at = ?", (int(time.time()) - 1,))
        conn.commit()
    with pytest.raises(DeviceAuthorizationError):
        registry.enroll(pairing_code=code, device_id="d1", name="One", os_type="ubuntu", public_key=public_key())


def test_revoke_removes_device_from_active_queries():
    registry = DeviceRegistry()
    code = registry.create_pairing_token()["code"]
    registry.enroll(pairing_code=code, device_id="d1", name="One", os_type="ubuntu", public_key=public_key())
    assert registry.revoke("d1").status == "revoked"
    assert registry.list_active() == []
    with pytest.raises(DeviceAuthorizationError):
        registry.assert_authorized("d1")


def test_heartbeat_expiry_is_fail_closed():
    registry = DeviceRegistry(heartbeat_ttl_seconds=1)
    code = registry.create_pairing_token()["code"]
    registry.enroll(pairing_code=code, device_id="d1", name="One", os_type="ubuntu", public_key=public_key())
    registry.heartbeat("d1")
    time.sleep(1.1)
    assert registry.list_active() == []
    assert registry.get("d1").status == "expired"
    with pytest.raises(DeviceAuthorizationError):
        registry.assert_authorized("d1")


def test_invalid_public_key_is_rejected():
    registry = DeviceRegistry()
    code = registry.create_pairing_token()["code"]
    with pytest.raises(ValueError):
        registry.enroll(pairing_code=code, device_id="d1", name="One", os_type="ubuntu", public_key="not-a-key")


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
    code = registry.create_pairing_token()["code"]
    device = registry.enroll(pairing_code=code, device_id="d1", name="One", os_type="Ubuntu", public_key=public_key()).device
    assert device.os_type == "ubuntu"
    code2 = registry.create_pairing_token()["code"]
    with pytest.raises(ValueError):
        registry.enroll(pairing_code=code2, device_id="d2", name="Two", os_type="ios", public_key=public_key())