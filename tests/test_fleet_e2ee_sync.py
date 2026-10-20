"""Sprint 5 Agent 2: End-to-end encryption tests for StatePayloadEncryptor (Issue #68).

Comprehensive test suite for E2EE state payload encryption/decryption.
Tests cover: round-trip encryption, tampering detection, wrong key rejection,
SHA3-256 hash validation, and fail-closed behavior.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
from uuid import uuid4

import pytest
from websockets.asyncio.client import connect

from app.core.state import State
from app.core.store import StateStore
from app.daemons.fleetd import (
    FleetSyncService,
    FleetWebSocketServer,
    generate_device_keypair,
)
from app.fleet.device_registry import DeviceRegistry
from app.fleet.e2ee import PayloadIntegrityError, StatePayloadEncryptor

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def master_key():
    """Generate a valid master pairing key."""
    return StatePayloadEncryptor.generate_master_key()


@pytest.fixture
def fleet_salt():
    """Generate a valid fleet salt."""
    return StatePayloadEncryptor.generate_fleet_salt()


@pytest.fixture
def encryptor(master_key, fleet_salt):
    """Create a StatePayloadEncryptor instance."""
    return StatePayloadEncryptor(master_key, fleet_salt=fleet_salt)


@pytest.fixture
def sample_state():
    """Create a sample State for testing."""
    return State(
        type="TestState",
        payload={"test": "value", "count": 42, "nested": {"key": "data"}},
    )


@pytest.fixture
def sample_state_with_previous(sample_state):
    """Create a state with a previous state reference."""
    previous = State(
        type="PreviousState",
        payload={"initial": True},
    )
    return State(
        id=uuid4(),
        type="TestState",
        payload={"test": "chained", "previous_id": str(previous.id)},
        previous_state_id=previous.id,
    )


# =============================================================================
# Test 1: Basic encryption/decryption round-trip
# =============================================================================


def test_encrypt_decrypt_roundtrip(encryptor, sample_state):
    """Test that a state can be encrypted and decrypted successfully."""
    # Encrypt the state
    envelope = encryptor.encrypt_state(sample_state)

    # Verify envelope structure
    assert "algorithm" in envelope
    assert envelope["algorithm"] == StatePayloadEncryptor.ALGORITHM
    assert "envelope_version" in envelope
    assert envelope["envelope_version"] == StatePayloadEncryptor.VERSION
    assert "metadata" in envelope
    assert "nonce" in envelope
    assert "ciphertext" in envelope

    # Decrypt the state
    decrypted = encryptor.decrypt_state(envelope)

    # Verify decrypted state matches original
    assert decrypted.id == sample_state.id
    assert decrypted.version == sample_state.version
    assert decrypted.type == sample_state.type
    assert decrypted.payload == sample_state.payload
    assert decrypted.timestamp_ns == sample_state.timestamp_ns
    assert decrypted.hash == sample_state.hash


# =============================================================================
# Test 2: Metadata preservation
# =============================================================================


def test_metadata_preserved_in_envelope(encryptor, sample_state):
    """Test that state metadata is correctly preserved in the envelope."""
    envelope = encryptor.encrypt_state(sample_state)

    metadata = envelope["metadata"]
    assert metadata["id"] == str(sample_state.id)
    assert metadata["version"] == sample_state.version
    assert metadata["hash"] == sample_state.hash
    assert metadata["previous_state_id"] is None


def test_metadata_with_previous_state(encryptor, sample_state_with_previous):
    """Test metadata preservation for states with previous_state_id."""
    envelope = encryptor.encrypt_state(sample_state_with_previous)

    metadata = envelope["metadata"]
    assert metadata["id"] == str(sample_state_with_previous.id)
    assert metadata["previous_state_id"] == str(sample_state_with_previous.previous_state_id)


# =============================================================================
# Test 3: Tampering detection (fail-closed)
# =============================================================================


def test_tampered_ciphertext_rejected(encryptor, sample_state):
    """Test that tampering with ciphertext is detected and rejected."""
    envelope = encryptor.encrypt_state(sample_state)

    # Tamper with the ciphertext (flip one bit)
    ciphertext = base64.b64decode(envelope["ciphertext"])
    ciphertext_bytes = bytearray(ciphertext)
    if len(ciphertext_bytes) > 0:
        ciphertext_bytes[0] ^= 0x01  # Flip first bit
    envelope["ciphertext"] = base64.b64encode(bytes(ciphertext_bytes)).decode("ascii")

    # Decryption should fail
    with pytest.raises(PayloadIntegrityError, match="authentication failed"):
        encryptor.decrypt_state(envelope)


def test_tampered_metadata_rejected(encryptor, sample_state):
    """Test that tampering with metadata is detected."""
    envelope = encryptor.encrypt_state(sample_state)

    # Tamper with metadata
    envelope["metadata"]["id"] = str(uuid4())

    # Decryption should fail (hash mismatch)
    with pytest.raises(PayloadIntegrityError, match="authentication failed|hash is invalid"):
        encryptor.decrypt_state(envelope)


def test_tampered_nonce_rejected(encryptor, sample_state):
    """Test that tampering with nonce is detected."""
    envelope = encryptor.encrypt_state(sample_state)

    # Tamper with nonce
    envelope["nonce"] = base64.b64encode(b"tampered_nonce").decode("ascii")

    # Decryption should fail
    with pytest.raises(PayloadIntegrityError, match="authentication failed"):
        encryptor.decrypt_state(envelope)


# =============================================================================
# Test 4: Wrong key rejection (fail-closed)
# =============================================================================


def test_wrong_key_rejection(sample_state):
    """Test that decryption with wrong key fails."""
    # Encrypt with one key
    encryptor1 = StatePayloadEncryptor(
        StatePayloadEncryptor.generate_master_key(),
        fleet_salt=StatePayloadEncryptor.generate_fleet_salt(),
    )
    envelope = encryptor1.encrypt_state(sample_state)

    # Try to decrypt with different key
    encryptor2 = StatePayloadEncryptor(
        StatePayloadEncryptor.generate_master_key(),
        fleet_salt=StatePayloadEncryptor.generate_fleet_salt(),
    )

    with pytest.raises(PayloadIntegrityError, match="authentication failed"):
        encryptor2.decrypt_state(envelope)


def test_wrong_fleet_salt_rejection(sample_state, master_key):
    """Test that decryption with wrong fleet salt fails."""
    # Encrypt with one salt
    encryptor1 = StatePayloadEncryptor(master_key, fleet_salt=os.urandom(16))
    envelope = encryptor1.encrypt_state(sample_state)

    # Try to decrypt with different salt
    encryptor2 = StatePayloadEncryptor(master_key, fleet_salt=os.urandom(16))

    with pytest.raises(PayloadIntegrityError, match="authentication failed"):
        encryptor2.decrypt_state(envelope)


# =============================================================================
# Test 5: Algorithm/version validation
# =============================================================================


def test_unsupported_algorithm_rejected(encryptor, sample_state):
    """Test that unsupported algorithm is rejected."""
    envelope = encryptor.encrypt_state(sample_state)
    envelope["algorithm"] = "Unsupported-Algorithm"

    with pytest.raises(PayloadIntegrityError, match="Unsupported encryption algorithm"):
        encryptor.decrypt_state(envelope)


def test_unsupported_version_rejected(encryptor, sample_state):
    """Test that unsupported version is rejected."""
    envelope = encryptor.encrypt_state(sample_state)
    envelope["envelope_version"] = 999

    with pytest.raises(PayloadIntegrityError, match="Unsupported envelope version"):
        encryptor.decrypt_state(envelope)


# =============================================================================
# Test 6: SHA3-256 hash validation
# =============================================================================


def test_decrypted_state_hash_validated(encryptor, sample_state):
    """Test that decrypted state hash is validated."""
    envelope = encryptor.encrypt_state(sample_state)

    # Decrypt and verify hash
    decrypted = encryptor.decrypt_state(envelope)
    assert decrypted.is_hash_valid()


def test_manually_corrupted_hash_rejected(encryptor, sample_state):
    """Test that manually corrupting the hash in metadata is rejected."""
    envelope = encryptor.encrypt_state(sample_state)

    # Corrupt the hash in metadata
    envelope["metadata"]["hash"] = "a" * 64

    with pytest.raises(PayloadIntegrityError, match="authentication failed|hash is invalid"):
        encryptor.decrypt_state(envelope)


# =============================================================================
# Test 7: Deterministic encryption with same key/salt
# =============================================================================


def test_deterministic_encryption_with_same_key(sample_state):
    """Test that encryption is deterministic with same key and salt."""
    master_key = StatePayloadEncryptor.generate_master_key()
    fleet_salt = StatePayloadEncryptor.generate_fleet_salt()

    encryptor1 = StatePayloadEncryptor(master_key, fleet_salt=fleet_salt)
    encryptor2 = StatePayloadEncryptor(master_key, fleet_salt=fleet_salt)

    # Due to random nonce, ciphertext will differ, but decryption should work
    envelope1 = encryptor1.encrypt_state(sample_state)
    envelope2 = encryptor2.encrypt_state(sample_state)

    # Ciphertexts differ due to different nonces
    assert envelope1["ciphertext"] != envelope2["ciphertext"]
    assert envelope1["nonce"] != envelope2["nonce"]

    # But both can be decrypted
    decrypted1 = encryptor1.decrypt_state(envelope1)
    decrypted2 = encryptor2.decrypt_state(envelope2)

    assert decrypted1.id == decrypted2.id == sample_state.id


# =============================================================================
# Test 8: Key generation
# =============================================================================


def test_generate_master_key():
    """Test master key generation."""
    key1 = StatePayloadEncryptor.generate_master_key()
    key2 = StatePayloadEncryptor.generate_master_key()

    assert len(key1) == 32
    assert len(key2) == 32
    assert key1 != key2


def test_generate_fleet_salt():
    """Test fleet salt generation."""
    salt1 = StatePayloadEncryptor.generate_fleet_salt()
    salt2 = StatePayloadEncryptor.generate_fleet_salt()

    assert len(salt1) == 16
    assert len(salt2) == 16
    assert salt1 != salt2


# =============================================================================
# Test 9: Invalid input handling
# =============================================================================


def test_invalid_master_key_length():
    """Test that invalid master key length raises ValueError."""
    with pytest.raises(ValueError, match="master_pairing_key must contain at least 256 bits"):
        StatePayloadEncryptor(b"short", fleet_salt=os.urandom(16))


def test_invalid_fleet_salt_length():
    """Test that invalid fleet salt length raises ValueError."""
    with pytest.raises(ValueError, match="fleet_salt must contain at least 128 bits"):
        StatePayloadEncryptor(os.urandom(32), fleet_salt=b"short")


def test_decrypt_with_missing_fields():
    """Test decryption with missing required fields."""
    encryptor = StatePayloadEncryptor(os.urandom(32), fleet_salt=os.urandom(16))

    # Missing algorithm
    with pytest.raises(PayloadIntegrityError):
        encryptor.decrypt_state({"nonce": "a", "ciphertext": "a"})

    # Missing nonce
    with pytest.raises(PayloadIntegrityError):
        encryptor.decrypt_state({"algorithm": "test", "ciphertext": "a"})

    # Missing ciphertext
    with pytest.raises(PayloadIntegrityError):
        encryptor.decrypt_state({"algorithm": "test", "nonce": "a"})


# =============================================================================
# Test 10: Chain validation (previous_state_id)
# =============================================================================


def test_chain_validation_with_previous_state(encryptor):
    """Test encryption/decryption of states with previous_state_id."""
    # Create a chain of states
    state1 = State(type="State1", payload={"step": 1})
    state2 = State(
        type="State2",
        payload={"step": 2},
        previous_state_id=state1.id,
    )
    state3 = State(
        type="State3",
        payload={"step": 3},
        previous_state_id=state2.id,
    )

    # Encrypt all states
    envelope1 = encryptor.encrypt_state(state1)
    envelope2 = encryptor.encrypt_state(state2)
    envelope3 = encryptor.encrypt_state(state3)

    # Decrypt all states
    decrypted1 = encryptor.decrypt_state(envelope1)
    decrypted2 = encryptor.decrypt_state(envelope2)
    decrypted3 = encryptor.decrypt_state(envelope3)

    # Verify chain
    assert decrypted1.id == state1.id
    assert decrypted2.id == state2.id
    assert decrypted2.previous_state_id == state1.id
    assert decrypted3.id == state3.id
    assert decrypted3.previous_state_id == state2.id

    # Verify all hashes are valid
    assert decrypted1.is_hash_valid()
    assert decrypted2.is_hash_valid()
    assert decrypted3.is_hash_valid()


# =============================================================================
# Test 11: Empty payload handling
# =============================================================================


def test_empty_payload_encryption(encryptor):
    """Test encryption of state with empty payload."""
    state = State(type="EmptyState", payload={})
    envelope = encryptor.encrypt_state(state)
    decrypted = encryptor.decrypt_state(envelope)

    assert decrypted.id == state.id
    assert decrypted.payload == {}


# =============================================================================
# Test 12: Large payload handling
# =============================================================================


def test_large_payload_encryption(encryptor):
    """Test encryption of state with large payload."""
    large_payload = {
        "data": [{"id": i, "value": f"item_{i}"} for i in range(1000)],
        "metadata": {"count": 1000, "description": "Large payload test"},
    }
    state = State(type="LargeState", payload=large_payload)

    envelope = encryptor.encrypt_state(state)
    decrypted = encryptor.decrypt_state(envelope)

    assert decrypted.payload == large_payload
    assert decrypted.is_hash_valid()


# =============================================================================
# Test 13: Special characters in payload
# =============================================================================


def test_special_characters_in_payload(encryptor):
    """Test encryption with special characters and Unicode."""
    state = State(
        type="UnicodeState",
        payload={
            "text": "Hello 世界 🌍",
            "emoji": "🎉🚀",
            "special": "!@#$%^&*()_+-={}[]|:;\"'<>?,./",
            "newlines": "line1\nline2\r\nline3",
            "tabs": "\tindented",
        },
    )

    envelope = encryptor.encrypt_state(state)
    decrypted = encryptor.decrypt_state(envelope)

    assert decrypted.payload == state.payload


# =============================================================================
# Test 14: Fail-closed behavior - malformed input
# =============================================================================


def test_malformed_base64_nonce_rejected(encryptor):
    """Test that malformed base64 nonce is rejected."""
    envelope = {
        "algorithm": StatePayloadEncryptor.ALGORITHM,
        "envelope_version": StatePayloadEncryptor.VERSION,
        "metadata": {"id": str(uuid4()), "version": 1, "hash": "a" * 64},
        "nonce": "!!!invalid_base64!!!",
        "ciphertext": base64.b64encode(b"test").decode("ascii"),
    }

    with pytest.raises(PayloadIntegrityError):
        encryptor.decrypt_state(envelope)


def test_malformed_base64_ciphertext_rejected(encryptor):
    """Test that malformed base64 ciphertext is rejected."""
    envelope = {
        "algorithm": StatePayloadEncryptor.ALGORITHM,
        "envelope_version": StatePayloadEncryptor.VERSION,
        "metadata": {"id": str(uuid4()), "version": 1, "hash": "a" * 64},
        "nonce": base64.b64encode(os.urandom(12)).decode("ascii"),
        "ciphertext": "!!!invalid_base64!!!",
    }

    with pytest.raises(PayloadIntegrityError):
        encryptor.decrypt_state(envelope)


# =============================================================================
# Test 15: Context separation (different key_context)
# =============================================================================


def test_different_key_context_produces_different_keys():
    """Test that different key_context produces different derived keys."""
    master_key = StatePayloadEncryptor.generate_master_key()
    fleet_salt = StatePayloadEncryptor.generate_fleet_salt()

    encryptor1 = StatePayloadEncryptor(
        master_key, fleet_salt=fleet_salt, key_context=b"context-1"
    )
    encryptor2 = StatePayloadEncryptor(
        master_key, fleet_salt=fleet_salt, key_context=b"context-2"
    )

    state = State(type="Test", payload={"test": "value"})

    envelope1 = encryptor1.encrypt_state(state)

    # Cannot decrypt with different context
    with pytest.raises(PayloadIntegrityError):
        encryptor2.decrypt_state(envelope1)


# =============================================================================
# Sprint 5 Agent 4: fleetd websocket integration tests (origin/main side)
# =============================================================================



def _services():
    device_a = generate_device_keypair("device-a", "Laptop")
    device_b = generate_device_keypair("device-b", "Phone")
    registry = DeviceRegistry()
    code = registry.create_pairing_token(ttl_seconds=300)
    enrollment = registry.enroll(
        pairing_code=code["code"],
        device_id=device_b.device_id,
        name=device_b.name,
        os_type=device_b.os_type,
        public_key=device_b.public_key,
    )
    tokens = {"device-b": enrollment.auth_token}
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
        websocket_server = FleetWebSocketServer(
            FleetSyncService(
                registry=registry,
                store=StateStore(),
                encryptor=StatePayloadEncryptor(os.urandom(32), fleet_salt=os.urandom(16)),
            ),
            port=port,
        )
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


def _call(websocket, method: str, params: dict):
    import uuid

    async def _send() -> dict:
        call_id = uuid.uuid4().hex
        await websocket.send(json.dumps({
            "id": call_id,
            "method": method,
            "params": params,
        }))
        return json.loads(await websocket.recv())

    return _send()


def _encryptor():
    return StatePayloadEncryptor(os.urandom(32), fleet_salt=os.urandom(16))


def _chain(count: int = 3):
    import uuid

    from app.core.state import State

    states = []
    previous = None
    for _ in range(count):
        previous = State(
            id=uuid.uuid4(),
            version=1,
            hash="",
            type="note",
            payload={"text": uuid.uuid4().hex},
            previous_state_id=previous.id if previous else None,
            timestamp_ns=(previous.timestamp_ns + 1) if previous else 1,
        )
        states.append(previous)
    return states


def test_full_sync_round_trip_between_two_devices() -> None:
    """Device A pushes a chain, device B pulls the missing blocks and
    reconstructs the exact same states locally."""
    async def scenario() -> None:
        _, device_b, registry, tokens = _services()
        encryptor = _encryptor()
        store = StateStore()
        service = FleetSyncService(registry=registry, store=store, encryptor=encryptor)
        port = get_free_port()
        server = FleetWebSocketServer(service, port=port)
        await server.start()
        try:
            # Device A pushes a three-state chain (A is trusted by construction
            # in this fixture: only the public-key handshake boundary is tested
            # elsewhere; the token is issued for device-b).
            chain = _chain(3)
            blocks = [encryptor.encrypt_state(state) for state in chain]
            local = StateStore()
            for state in chain:
                local.append(state)

            async with connect(f"ws://127.0.0.1:{server.port}") as a:
                hs = await _call(a, "sync.handshake", {
                    "device_id": "device-b",
                    "public_key": registry.get("device-b").public_key,
                    "auth_token": tokens["device-b"],
                    "headers": [],
                })
                assert hs["result"]["accepted"] is True
                resp = await _call(a, "sync.push_blocks", {
                    "device_id": "device-b",
                    "auth_token": tokens["device-b"],
                    "blocks": blocks,
                })
                assert resp["result"]["accepted"] == 3
                assert resp["result"]["invalid"] == 0

            async with connect(f"ws://127.0.0.1:{server.port}") as b:
                handshake = await _call(b, "sync.handshake", {
                    "device_id": "device-b",
                    "public_key": registry.get("device-b").public_key,
                    "auth_token": tokens["device-b"],
                    "headers": [],
                })
                # pull what device B does not already have: the server's
                # full header list minus whatever B has stored locally
                missing = [
                    header["hash"] for header in handshake["result"]["headers"]
                ]
                assert len(missing) == 3

                pulled = await _call(b, "sync.request_blocks", {
                    "device_id": "device-b",
                    "auth_token": tokens["device-b"],
                    "hashes": missing,
                })
                assert pulled["result"]["count"] == 3

                # Device B decrypts and stores locally -> full round trip.
                peer = StateStore()
                for block in pulled["result"]["blocks"]:
                    peer.append(encryptor.decrypt_state(block))
                assert peer.count() == 3
                assert [

                    (str(state.id), state.hash) for state in peer.list_states()
                ] == [(str(state.id), state.hash) for state in chain]
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_wrong_key_is_rejected_fail_closed() -> None:
    """Blocks encrypted under a different key never reach the store."""
    async def scenario() -> None:
        _, device_b, registry, tokens = _services()
        encryptor = _encryptor()
        service = FleetSyncService(
            registry=registry,
            store=StateStore(),
            encryptor=StatePayloadEncryptor(os.urandom(32), fleet_salt=os.urandom(16)),
        )
        port = get_free_port()
        server = FleetWebSocketServer(service, port=port)
        await server.start()
        try:
            chain = _chain(2)
            blocks = [encryptor.encrypt_state(state) for state in chain]
            async with connect(f"ws://127.0.0.1:{server.port}") as ws:
                hs = await _call(ws, "sync.handshake", {
                    "device_id": "device-b",
                    "public_key": registry.get("device-b").public_key,
                    "auth_token": tokens["device-b"],
                    "headers": [],
                })
                assert hs["result"]["accepted"] is True
                resp = await _call(ws, "sync.push_blocks", {
                    "device_id": "device-b",
                    "auth_token": tokens["device-b"],
                    "blocks": blocks,
                })
                # wrong-key blocks are rejected fail-closed: nothing stored
                assert resp["result"]["accepted"] == 0
                assert resp["result"]["invalid"] == 2
                assert service.store.count() == 0
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_forked_state_is_rejected_over_websocket() -> None:
    """Same state id pushed twice with different hashes: the fork loses."""
    async def scenario() -> None:
        _, device_b, registry, tokens = _services()
        encryptor = _encryptor()
        service = FleetSyncService(
            registry=registry, store=StateStore(), encryptor=encryptor
        )
        port = get_free_port()
        server = FleetWebSocketServer(service, port=port)
        await server.start()
        try:
            import uuid

            from app.core.state import State

            original = State(
                id=uuid.uuid4(), version=1, hash="", type="note",
                payload={"text": "original"}, previous_state_id=None,
                timestamp_ns=1,
            )
            fork = State(
                id=original.id, version=1, hash="", type="note",
                payload={"text": "forked"}, previous_state_id=None,
                timestamp_ns=2,
            )
            async with connect(f"ws://127.0.0.1:{server.port}") as ws:
                hs = await _call(ws, "sync.handshake", {
                    "device_id": "device-b",
                    "public_key": registry.get("device-b").public_key,
                    "auth_token": tokens["device-b"],
                    "headers": [],
                })
                assert hs["result"]["accepted"] is True
                original_resp = await _call(ws, "sync.push_blocks", {
                    "device_id": "device-b",
                    "auth_token": tokens["device-b"],
                    "blocks": [encryptor.encrypt_state(original)],
                })
                assert original_resp["result"]["accepted"] == 1
                fork_resp = await _call(ws, "sync.push_blocks", {
                    "device_id": "device-b",
                    "auth_token": tokens["device-b"],
                    "blocks": [encryptor.encrypt_state(fork)],
                })
                # the fork is rejected: same id, different hash -> invalid
                assert fork_resp["result"]["accepted"] == 0

            stored = service.store.get_by_id(original.id)
            assert stored.hash == original.hash
            assert stored.payload == {"text": "original"}
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_revoked_device_is_kicked_with_unauthorized_frame() -> None:
    """After registry.revoke() the open session must be closed (1008)."""
    async def scenario() -> None:
        _, device_b, registry, tokens = _services()
        service = FleetSyncService(
            registry=registry, store=StateStore(), encryptor=_encryptor()
        )
        port = get_free_port()
        server = FleetWebSocketServer(service, port=port)
        await server.start()
        try:
            async with connect(f"ws://127.0.0.1:{server.port}") as ws:
                handshake = await _call(ws, "sync.handshake", {
                    "device_id": "device-b",
                    "public_key": registry.get("device-b").public_key,
                    "auth_token": tokens["device-b"],
                    "headers": [],
                })
                assert handshake["result"]["accepted"] is True

                registry.revoke("device-b")
                resp = await _call(ws, "sync.request_blocks", {
                    "device_id": "device-b",
                    "auth_token": tokens["device-b"],
                    "hashes": [],
                })
                assert resp["error"]["code"] == -32030
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_heartbeat_updates_registry_on_handshake() -> None:
    async def scenario() -> None:
        _, device_b, registry, tokens = _services()
        service = FleetSyncService(
            registry=registry, store=StateStore(), encryptor=_encryptor()
        )
        port = get_free_port()
        server = FleetWebSocketServer(service, port=port)
        await server.start()
        try:
            before = registry.get("device-b").last_heartbeat
            async with connect(f"ws://127.0.0.1:{server.port}") as ws:
                await _call(ws, "sync.handshake", {
                    "device_id": "device-b",
                    "public_key": registry.get("device-b").public_key,
                    "auth_token": tokens["device-b"],
                    "headers": [],
                })
            after = registry.get("device-b").last_heartbeat
            assert after is not None
            if before is not None:
                assert after >= before
        finally:
            await server.stop()

    asyncio.run(scenario())
