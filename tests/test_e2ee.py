"""Unit tests for fleet StatePayloadEncryptor (Sprint 5 Task 5.2 / #68)."""

from __future__ import annotations

import base64
import os

import pytest

from app.core.state import State
from app.fleet.e2ee import (
    NonceReuseError,
    PayloadIntegrityError,
    StatePayloadEncryptor,
)


def _encryptor(
    master: bytes | None = None,
    salt: bytes | None = None,
    **kwargs,
) -> StatePayloadEncryptor:
    return StatePayloadEncryptor(
        master or os.urandom(32),
        fleet_salt=salt or os.urandom(16),
        **kwargs,
    )


def _state(**payload_overrides) -> State:
    payload = {"title": "Byggetilladelse", "amount": 42}
    payload.update(payload_overrides)
    return State(type="building_permit", payload=payload)


def test_encrypt_decrypt_roundtrip_preserves_cleartext_metadata():
    enc = _encryptor()
    original = _state()
    envelope = enc.encrypt_state(original)

    assert envelope["metadata"]["id"] == str(original.id)
    assert envelope["metadata"]["version"] == original.version
    assert envelope["metadata"]["hash"] == original.hash
    assert "payload" not in envelope
    assert "ciphertext" in envelope

    restored = enc.decrypt_state(envelope)
    assert restored.id == original.id
    assert restored.version == original.version
    assert restored.hash == original.hash
    assert restored.payload == original.payload
    assert restored.type == original.type


def test_wrong_key_fails_decryption():
    salt = os.urandom(16)
    sender = _encryptor(os.urandom(32), salt)
    wrong = _encryptor(os.urandom(32), salt)
    envelope = sender.encrypt_state(_state())

    with pytest.raises(PayloadIntegrityError):
        wrong.decrypt_state(envelope)


def test_tampered_ciphertext_fails_integrity():
    enc = _encryptor()
    envelope = enc.encrypt_state(_state())
    raw = bytearray(base64.b64decode(envelope["ciphertext"]))
    raw[-1] ^= 0x01
    envelope["ciphertext"] = base64.b64encode(bytes(raw)).decode("ascii")

    with pytest.raises(PayloadIntegrityError):
        enc.decrypt_state(envelope)


def test_tampered_cleartext_metadata_fails_integrity():
    enc = _encryptor()
    envelope = enc.encrypt_state(_state())
    envelope["metadata"] = dict(envelope["metadata"])
    envelope["metadata"]["hash"] = "0" * 64

    with pytest.raises(PayloadIntegrityError):
        enc.decrypt_state(envelope)


def test_empty_payload_fail_closed_on_encrypt():
    enc = _encryptor()
    empty = State(type="empty", payload={})
    with pytest.raises(PayloadIntegrityError, match="empty"):
        enc.encrypt_state(empty)


def test_missing_ciphertext_fail_closed_on_decrypt():
    enc = _encryptor()
    envelope = enc.encrypt_state(_state())
    del envelope["ciphertext"]
    with pytest.raises(PayloadIntegrityError):
        enc.decrypt_state(envelope)


def test_nonce_is_never_reused_with_same_key():
    enc = _encryptor()
    fixed = os.urandom(12)
    enc.encrypt_state(_state(title="first"), nonce=fixed)

    with pytest.raises(NonceReuseError):
        enc.encrypt_state(_state(title="second"), nonce=fixed)


def test_random_nonces_differ_across_encrypts():
    enc = _encryptor()
    a = enc.encrypt_state(_state(title="a"))
    b = enc.encrypt_state(_state(title="b"))
    assert a["nonce"] != b["nonce"]


def test_device_pair_derives_distinct_keys():
    master = os.urandom(32)
    salt = os.urandom(16)
    pair_ab = StatePayloadEncryptor(
        master,
        fleet_salt=salt,
        local_device_id="device-a",
        peer_device_id="device-b",
    )
    pair_ac = StatePayloadEncryptor(
        master,
        fleet_salt=salt,
        local_device_id="device-a",
        peer_device_id="device-c",
    )
    envelope = pair_ab.encrypt_state(_state())
    with pytest.raises(PayloadIntegrityError):
        pair_ac.decrypt_state(envelope)

    pair_ba = StatePayloadEncryptor(
        master,
        fleet_salt=salt,
        local_device_id="device-b",
        peer_device_id="device-a",
    )
    restored = pair_ba.decrypt_state(envelope)
    assert restored.payload["title"] == "Byggetilladelse"
