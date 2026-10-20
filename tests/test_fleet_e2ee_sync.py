"""Sprint 5 Agent 2: End-to-end encryption tests for StatePayloadEncryptor (Issue #68).

Comprehensive test suite for E2EE state payload encryption/decryption.
Tests cover: round-trip encryption, tampering detection, wrong key rejection,
SHA3-256 hash validation, and fail-closed behavior.
"""

from __future__ import annotations

import base64
import os
from uuid import uuid4

import pytest

from app.core.state import State
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
