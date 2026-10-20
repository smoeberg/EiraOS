"""Sprint 5 / Task 5.5: service-level fleet sync tests (mocked adapters).

The registry and encryptor are replaced by fake adapters that implement the
same interfaces as ``app.fleet.device_registry.DeviceRegistry`` and
``app.fleet.e2ee.StatePayloadEncryptor`` so the sync protocol can be tested
without device pairing or real cryptography. The E2EE path is exercised end to
end (with the real implementations) in ``tests/test_fleet_e2ee_sync.py``.
"""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any, Mapping

import pytest

from app.core.state import State
from app.core.store import StateStore
from app.daemons.fleetd import FleetSyncService
from app.fleet.device_registry import DeviceAuthorizationError
from app.fleet.e2ee import PayloadIntegrityError
from app.fleet.merkle_sync import MerkleSyncEngine


class FakeRegistry:
    """Adapter stand-in for DeviceRegistry: pairing + heartbeat bookkeeping."""

    def __init__(self, active: set[str] | None = None) -> None:
        self.active = set(active or set())
        self.heartbeats: list[str] = []
        self.revoked: set[str] = set()

    def assert_authorized(
        self,
        device_id: str,
        *,
        public_key: str | None = None,
        auth_token: str | None = None,
        require_token: bool = False,
    ) -> Any:
        if device_id not in self.active or device_id in self.revoked:
            raise DeviceAuthorizationError("Device is not paired")
        if require_token and not auth_token:
            raise DeviceAuthorizationError("Device authentication token is required")
        return device_id

    def heartbeat(self, device_id: str) -> str:
        self.assert_authorized(device_id)
        self.heartbeats.append(device_id)
        return device_id

    def revoke(self, device_id: str) -> None:
        self.revoked.add(device_id)


class FakeEncryptor:
    """Adapter stand-in for StatePayloadEncryptor: reversible, tamper-aware.

    Blocks are base64-encoded canonical JSON. Any modification of the encoded
    payload (or of the metadata stored alongside it) fails decryption, which
    mirrors the authenticated-encryption behaviour of the real encryptor.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _encode(self, state: State) -> Mapping[str, Any]:
        return {
            "metadata": {
                "id": str(state.id),
                "version": state.version,
                "hash": state.hash,
                "previous_state_id": (
                    str(state.previous_state_id) if state.previous_state_id else None
                ),
            },
            "timestamp_ns": state.timestamp_ns,
            "body": base64.b64encode(
                json.dumps(
                    state.payload, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).decode("ascii"),
        }

    def encrypt_state(self, state: State) -> dict[str, Any]:
        self.calls.append("encrypt")
        return dict(self._encode(state))

    def decrypt_state(self, envelope: Mapping[str, Any]) -> State:
        self.calls.append("decrypt")
        try:
            metadata = dict(envelope["metadata"])
            payload = json.loads(
                base64.b64decode(str(envelope["body"]), validate=True).decode("utf-8")
            )
        except (KeyError, ValueError, TypeError, UnicodeDecodeError) as exc:
            raise PayloadIntegrityError(str(exc)) from exc
        previous = metadata.get("previous_state_id")
        state = State(
            id=uuid.UUID(str(metadata["id"])),
            version=int(metadata["version"]),
            hash=str(metadata["hash"]),
            type="note",
            payload=payload,
            previous_state_id=uuid.UUID(previous) if previous else None,
            timestamp_ns=int(envelope.get("timestamp_ns", 0)),
        )
        if not state.is_hash_valid():
            raise PayloadIntegrityError("State hash does not match decrypted payload")
        return state


def signed_state(previous: State | None = None) -> State:
    """Build a state whose SHA3-256 hash matches its canonical content."""
    return State(
        id=uuid.uuid4(),
        version=1,
        hash="",
        type="note",
        payload={"text": uuid.uuid4().hex},
        previous_state_id=previous.id if previous else None,
        timestamp_ns=(previous.timestamp_ns + 1) if previous else 1,
    )


def make_service() -> tuple[FleetSyncService, FakeRegistry, FakeEncryptor]:
    registry = FakeRegistry(active={"device-a"})
    store = StateStore(":memory:")
    encryptor = FakeEncryptor()
    return FleetSyncService(registry=registry, store=store, encryptor=encryptor), registry, encryptor


def test_handshake_reports_merkle_diff_and_beats_heartbeat() -> None:
    service, registry, _ = make_service()
    s1 = signed_state()
    s2 = signed_state(s1)
    service.store.append(s1)
    service.store.append(s2)
    remote = [{"id": str(s1.id), "hash": s1.hash, "version": s1.version,
               "previous_state_id": None, "timestamp_ns": s1.timestamp_ns}]

    result = service.handshake({"device_id": "device-a", "auth_token": "tok", "headers": remote})

    assert result["accepted"] is True
    assert result["device_id"] == "device-a"
    assert result["root"] == MerkleSyncEngine().snapshot(service.store.list_states()).root
    assert s2.hash in result["offer_hashes"]  # local-only -> offered to remote
    assert s1.hash not in result["offer_hashes"]  # remote already has s1
    assert s1.hash in [header["hash"] for header in result["headers"]]
    assert registry.heartbeats == ["device-a"]


def test_handshake_requires_active_device() -> None:
    service, _, _ = make_service()
    with pytest.raises(DeviceAuthorizationError):
        service.handshake({"device_id": "device-x", "auth_token": "tok", "headers": []})


def test_request_blocks_returns_encrypted_blocks_for_known_hashes() -> None:
    service, _, _ = make_service()
    s1 = signed_state()
    service.store.append(s1)

    result = service.request_blocks(
        {"device_id": "device-a", "auth_token": "tok", "hashes": [s1.hash, "missing-hash"]}
    )

    assert result["count"] == 1
    assert result["blocks"][0]["metadata"]["hash"] == s1.hash


def test_request_blocks_rejects_unauthorized_device() -> None:
    service, _, _ = make_service()
    with pytest.raises(DeviceAuthorizationError):
        service.request_blocks({"device_id": "device-x", "auth_token": "tok", "hashes": []})


def test_push_blocks_accepts_blocks_arriving_out_of_order() -> None:
    service, _, _ = make_service()
    s1 = signed_state()
    s2 = signed_state(s1)
    blocks = [service.encryptor.encrypt_state(s2), service.encryptor.encrypt_state(s1)]

    result = service.push_blocks({"device_id": "device-a", "auth_token": "tok", "blocks": blocks})

    assert result["accepted"] == 2
    assert result["invalid"] == 0
    assert service.store.count() == 2
    assert result["root"] == MerkleSyncEngine().snapshot(service.store.list_states()).root


def test_push_blocks_skips_already_known_blocks() -> None:
    service, _, _ = make_service()
    s1 = signed_state()
    block = service.encryptor.encrypt_state(s1)
    service.push_blocks({"device_id": "device-a", "auth_token": "tok", "blocks": [block]})

    result = service.push_blocks({"device_id": "device-a", "auth_token": "tok", "blocks": [block]})

    assert result["skipped"] == 1
    assert result["accepted"] == 0
    assert service.store.count() == 1


def test_push_blocks_fail_closed_on_missing_chain_parent() -> None:
    service, _, _ = make_service()
    s1 = signed_state()
    s2 = signed_state(s1)  # parent never pushed
    blocks = [service.encryptor.encrypt_state(s2)]

    result = service.push_blocks({"device_id": "device-a", "auth_token": "tok", "blocks": blocks})

    assert result["accepted"] == 0
    assert result["invalid"] == 1
    assert service.store.count() == 0


def test_push_blocks_rejects_forked_state_id() -> None:
    """Same state id with a different hash must never overwrite the original."""
    service, _, _ = make_service()
    original = signed_state()
    service.push_blocks({"device_id": "device-a", "auth_token": "tok",
                         "blocks": [service.encryptor.encrypt_state(original)]})

    fork = signed_state()
    fork = State(
        id=original.id,  # same id, different content/hash
        version=fork.version,
        hash=fork.hash,
        type=fork.type,
        payload=fork.payload,
        previous_state_id=fork.previous_state_id,
        timestamp_ns=fork.timestamp_ns,
    )

    result = service.push_blocks(
        {"device_id": "device-a", "auth_token": "tok", "blocks": [service.encryptor.encrypt_state(fork)]}
    )

    assert result["invalid"] == 1
    assert result["accepted"] == 0
    assert service.store.get_by_id(original.id).hash == original.hash


def test_push_blocks_rejects_tampered_envelope() -> None:
    service, _, _ = make_service()
    s1 = signed_state()
    block = service.encryptor.encrypt_state(s1)
    body = json.loads(base64.b64decode(block["body"]).decode("utf-8"))
    body["payload"] = {"text": "tampered"}
    block["body"] = base64.b64encode(json.dumps(body).encode("utf-8")).decode("ascii")
    # body no longer matches base64-canonical round-trip -> decryption fails
    raw = json.dumps({"payload": {"text": "tampered"}}, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    block["body"] = base64.b64encode(raw).decode("ascii")

    result = service.push_blocks({"device_id": "device-a", "auth_token": "tok", "blocks": [block]})

    assert result["invalid"] == 1
    assert result["accepted"] == 0
    assert service.store.count() == 0


def test_unauthorized_push_never_touches_store() -> None:
    service, _, _ = make_service()
    s1 = signed_state()
    with pytest.raises(DeviceAuthorizationError):
        service.push_blocks({"device_id": "device-x", "auth_token": "tok",
                             "blocks": [service.encryptor.encrypt_state(s1)]})
    assert service.store.count() == 0


# Audit finding 1 (Major): a batch containing any invalid block must be
# rejected in its entirety — no partial inserts, and the response must
# report the number of invalid blocks. The current implementation applies
# the valid subset, so this contract test is expected to fail until
# Agent 9 lands the fix in app/daemons/fleetd.py (see fix plan).
@pytest.mark.xfail(reason="push_blocks applies partial inserts; reject-all fix is Agent 9's task")
def test_mixed_batch_is_rejected_in_full() -> None:
    service, _, encryptor = make_service()
    good = signed_state()
    forged = signed_state()
    forged.hash = "0" * 64  # hash does not match payload -> integrity failure

    result = service.push_blocks({
        "device_id": "device-a",
        "auth_token": "tok",
        "blocks": [
            encryptor.encrypt_state(good),
            encryptor.encrypt_state(forged),
        ],
    })

    # Contract: one bad block poisons the whole batch.
    assert result["accepted"] == 0
    assert result["invalid"] == 1
    assert service.store.count() == 0
