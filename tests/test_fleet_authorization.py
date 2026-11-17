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

import json

import pytest

from app.daemons import fleetd
from app.daemons.base import JsonRpcServer
from app.fleet.device_registry import (
    DeviceAuthorizationError,
    DeviceRegistry,
    device_fingerprint,
)
from app.ipc.socket_security import PeerCredentials
from tests.fleet_device import FleetTestDevice


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
        FleetTestDevice("Laptop").enrollment(code),
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
        FleetTestDevice("Laptop").enrollment(code),
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


def test_device_id_is_the_signing_key_fingerprint():
    registry = DeviceRegistry()
    device = FleetTestDevice("Laptop")
    enrolled = device.enroll(registry)
    assert enrolled.device_id == device_fingerprint(device.signing_key)


def test_new_key_cannot_claim_an_existing_device_id():
    registry = DeviceRegistry()
    victim_device = FleetTestDevice("Victim")
    victim = victim_device.enroll(registry)
    code = registry.create_pairing_token()["code"]
    attacker = FleetTestDevice("Attacker").enrollment(code) | {"device_id": victim.device_id}
    with pytest.raises(DeviceAuthorizationError, match="fingerprint"):
        registry.enroll(**attacker)
    # The refused attempt did not burn the code.
    FleetTestDevice("Next").enroll(registry, code)
    assert registry.get(victim.device_id).signing_key == victim_device.signing_key


def test_same_keys_cannot_enroll_twice():
    registry = DeviceRegistry()
    device = FleetTestDevice("One")
    device.enroll(registry)
    code = registry.create_pairing_token()["code"]
    with pytest.raises(DeviceAuthorizationError, match="already enrolled"):
        device.enroll(registry, code)
    FleetTestDevice("Three").enroll(registry, code)


def test_enrollment_needs_a_proof_with_the_signing_key():
    """F1c.1: someone who only knows a device's public keys cannot enroll
    them; the proof binds the pairing code to both keys."""
    registry = DeviceRegistry()
    code = registry.create_pairing_token()["code"]
    device, other = FleetTestDevice(), FleetTestDevice()
    request = device.enrollment(code)
    for forged in (
        request | {"proof": other.enrollment(code)["proof"]},
        request | {"public_key": other.public_key},
        request | {"pairing_code": registry.create_pairing_token()["code"]},
        request | {"proof": "bm90IGEgc2lnbmF0dXJl"},
    ):
        with pytest.raises(DeviceAuthorizationError, match="proof"):
            registry.enroll(**forged)
    assert registry.enroll(**request).device_id == device.device_id


def test_admin_group_is_created_without_members():
    """Packaging creates eira-fleet-admin but puts no user, the model or eira in it."""
    from pathlib import Path

    postinst = Path("packaging/debian/postinst").read_text()
    assert "addgroup --system eira-fleet-admin" in postinst
    for member in ("eira", "eira-model", '"$user"', "$USER"):
        assert f"adduser --quiet {member} eira-fleet-admin" not in postinst
        assert f"usermod -aG eira-fleet-admin {member}" not in postinst



# --- every sync call over IPC is signed over a single-use challenge (F1c.1) ---------


def _paired(server):
    from app.core.store import StateStore

    service = fleetd.default_sync_service()
    service.store = StateStore(":memory:")  # no stated in this test
    device = FleetTestDevice()
    device.enroll(service.registry)
    return device


def _sync(server, device, method, params=None, **kwargs):
    signed = device.signed(fleetd.default_sync_service().registry, method, params or {}, **kwargs)
    return call(server, method, signed, DESKTOP_USER)


def test_a_signed_handshake_over_ipc_is_accepted(server):
    device = _paired(server)
    reply = _sync(server, device, "sync.handshake", {"public_key": device.public_key, "headers": []})
    assert reply["result"]["accepted"] is True, reply


def test_a_challenge_over_ipc_is_given_only_to_a_paired_device(server):
    device = _paired(server)
    reply = call(server, "sync.challenge", {"device_id": device.device_id}, DESKTOP_USER)
    assert reply["result"]["nonce"]
    unknown = call(server, "sync.challenge", {"device_id": FleetTestDevice().device_id}, DESKTOP_USER)
    assert unknown["error"]["code"] == fleetd.FLEET_UNAUTHORIZED


@pytest.mark.parametrize("method", ["sync.handshake", "sync.request_blocks", "sync.push_blocks"])
def test_an_unsigned_or_token_call_over_ipc_is_refused(server, method):
    device = _paired(server)
    for params in ({"device_id": device.device_id},
                   {"device_id": device.device_id, "auth_token": "anything"}):
        reply = call(server, method, params, DESKTOP_USER)
        assert reply["error"]["code"] == fleetd.FLEET_UNAUTHORIZED, reply
