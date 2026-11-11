"""Fleet authorization attacks (security review, 11 November 2026).

Each test is an attack that worked before the fix:

* Any member of eira-clients (every desktop user and the model process) could
  create a pairing code, enroll a device of its own and revoke any device:
  ``_rpc_guard`` only translated errors, it never checked the caller.
* ``device_id`` was whatever the enrolling caller sent, so a new key could
  claim an existing device's id (EIRA-CONTEXT §1: the id is the key's
  fingerprint).
* The legacy ``fleet.enroll``/``heartbeat``/``device.get``/``list`` methods
  wrote an unauthenticated second device table next to the registry.
"""

from __future__ import annotations

import base64
import json
import os

import pytest

from app.daemons import fleetd
from app.daemons.base import JsonRpcServer
from app.fleet.device_registry import (
    DeviceAuthorizationError,
    DeviceRegistry,
    device_fingerprint,
)
from app.ipc.socket_security import PeerCredentials


def key() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("EIRA_FLEET_KEY_DIR", str(tmp_path))
    monkeypatch.setenv("EIRA_DEVICE_REGISTRY_DB", str(tmp_path / "devices.db"))
    monkeypatch.setenv("EIRA_FLEET_WS_ENABLED", "0")
    monkeypatch.setattr(fleetd, "_DEFAULT_SERVICE", None)
    srv = JsonRpcServer("fleetd", "fleetd")
    fleetd.register_fleet_handlers(srv)
    return srv


ADMIN_GID = 4242


@pytest.fixture
def admin_group(monkeypatch):
    monkeypatch.setattr(
        fleetd,
        "resolve_group_gid",
        lambda name: ADMIN_GID if name == fleetd.FLEET_ADMIN_GROUP else None,
    )


def call(srv, method, params, peer):
    line = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    return json.loads(srv.handle_line(line, peer=peer))


DESKTOP_USER = PeerCredentials(pid=1, uid=1000, gid=1000, groups=frozenset({1000}))
MODEL = PeerCredentials(pid=2, uid=998, gid=998, groups=frozenset({998}))
ADMIN = PeerCredentials(pid=3, uid=1001, gid=1001, groups=frozenset({1001, ADMIN_GID}))
ROOT = PeerCredentials(pid=4, uid=0, gid=0, groups=frozenset())


@pytest.mark.parametrize("peer", [DESKTOP_USER, MODEL, None])
def test_non_admin_cannot_create_pairing_code(server, admin_group, peer):
    response = call(server, "fleet.pairing.create", {}, peer)
    assert response["error"]["code"] == fleetd.FLEET_UNAUTHORIZED


@pytest.mark.parametrize("peer", [DESKTOP_USER, MODEL, None])
def test_non_admin_cannot_revoke_a_device(server, admin_group, peer):
    code = call(server, "fleet.pairing.create", {}, ADMIN)["result"]["code"]
    enrolled = call(
        server,
        "fleet.device.enroll",
        {"pairing_code": code, "name": "Laptop", "os_type": "ubuntu", "public_key": key()},
        DESKTOP_USER,
    )["result"]
    device_id = enrolled["device_id"]
    response = call(server, "fleet.device.revoke", {"device_id": device_id}, peer)
    assert response["error"]["code"] == fleetd.FLEET_UNAUTHORIZED
    assert fleetd.default_sync_service().registry.get(device_id).status == "active"


@pytest.mark.parametrize("peer", [ADMIN, ROOT])
def test_admin_and_root_can_pair_and_revoke(server, admin_group, peer):
    code = call(server, "fleet.pairing.create", {}, peer)["result"]["code"]
    enrolled = call(
        server,
        "fleet.device.enroll",
        {"pairing_code": code, "name": "Laptop", "os_type": "ubuntu", "public_key": key()},
        DESKTOP_USER,
    )["result"]
    device_id = enrolled["device_id"]
    revoked = call(server, "fleet.device.revoke", {"device_id": device_id}, peer)
    assert revoked["result"]["status"] == "revoked"


def test_missing_admin_group_fails_closed(server, monkeypatch):
    monkeypatch.setattr(fleetd, "resolve_group_gid", lambda name: None)
    response = call(server, "fleet.pairing.create", {}, ADMIN)
    assert response["error"]["code"] == fleetd.FLEET_UNAUTHORIZED


def test_client_supplied_peer_is_ignored(server, admin_group):
    """A caller cannot claim to be root by sending _peer in params."""
    response = call(
        server, "fleet.pairing.create", {"_peer": {"uid": 0, "gid": 0}}, DESKTOP_USER
    )
    assert response["error"]["code"] == fleetd.FLEET_UNAUTHORIZED


@pytest.mark.parametrize(
    "method", ["fleet.enroll", "fleet.heartbeat", "fleet.device.get", "fleet.list"]
)
def test_legacy_inventory_methods_are_gone(server, method):
    response = call(server, method, {"device_id": "x"}, DESKTOP_USER)
    assert "Unknown method" in response["error"]["message"]


def test_http_bridge_has_no_fleet_routes():
    from app.http_bridge import app

    assert not [r for r in app.routes if getattr(r, "path", "").startswith("/v1/fleet")]


def test_device_id_is_the_key_fingerprint():
    registry = DeviceRegistry()
    public_key = key()
    code = registry.create_pairing_token()["code"]
    enrolled = registry.enroll(
        pairing_code=code, name="Laptop", os_type="ubuntu", public_key=public_key
    )
    assert enrolled.device.device_id == device_fingerprint(public_key)


def test_new_key_cannot_claim_an_existing_device_id():
    registry = DeviceRegistry()
    victim_key = key()
    victim = registry.enroll(
        pairing_code=registry.create_pairing_token()["code"],
        name="Victim",
        os_type="ubuntu",
        public_key=victim_key,
    ).device
    code = registry.create_pairing_token()["code"]
    with pytest.raises(DeviceAuthorizationError, match="fingerprint"):
        registry.enroll(
            pairing_code=code,
            device_id=victim.device_id,
            name="Attacker",
            os_type="ubuntu",
            public_key=key(),
        )
    # The refused attempt did not burn the code.
    registry.enroll(pairing_code=code, name="Next", os_type="ubuntu", public_key=key())
    assert registry.get(victim.device_id).public_key == victim_key


def test_same_key_cannot_enroll_twice():
    registry = DeviceRegistry()
    public_key = key()
    registry.enroll(
        pairing_code=registry.create_pairing_token()["code"],
        name="One",
        os_type="ubuntu",
        public_key=public_key,
    )
    code = registry.create_pairing_token()["code"]
    with pytest.raises(DeviceAuthorizationError, match="already enrolled"):
        registry.enroll(pairing_code=code, name="Two", os_type="ubuntu", public_key=public_key)
    registry.enroll(pairing_code=code, name="Three", os_type="ubuntu", public_key=key())


def test_admin_group_is_created_without_members():
    """Packaging creates eira-fleet-admin but puts no user, the model or eira in it."""
    from pathlib import Path

    postinst = Path("packaging/debian/postinst").read_text()
    assert "addgroup --system eira-fleet-admin" in postinst
    for member in ("eira", "eira-model", '"$user"', "$USER"):
        assert f"adduser --quiet {member} eira-fleet-admin" not in postinst
        assert f"usermod -aG eira-fleet-admin {member}" not in postinst

