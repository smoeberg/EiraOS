"""End-to-end encryption for fleet state payloads.

Only the sensitive ``State.payload`` (plus type/timestamp needed to rebuild the
object) is encrypted.  Identifiers used for Merkle comparison — ``id``,
``version``, ``hash``, ``previous_state_id`` — stay in the clear envelope
header.

Keys are derived with HKDF-SHA256 from the caller's master fleet-sync key and
a per device-pair context.  Nonces are tracked so the same (key, nonce) pair is
never reused for encryption.
"""

from __future__ import annotations

import base64
import json
import os
import threading
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.state import State

_NONCE_SIZE = 12
_KEY_SIZE = 32
_MAX_NONCE_RETRIES = 8


class PayloadIntegrityError(ValueError):
    """Raised when an encrypted state cannot be authenticated or is incomplete."""


class NonceReuseError(ValueError):
    """Raised when encryption would reuse a nonce under the same derived key."""


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _pair_context(local_device_id: str | None, peer_device_id: str | None) -> bytes:
    """Stable HKDF info suffix for a directed device pair."""
    if not local_device_id and not peer_device_id:
        return b"state-payload"
    left = (local_device_id or "").strip()
    right = (peer_device_id or "").strip()
    ordered = "\x1f".join(sorted((left, right)))
    return f"state-payload\x00pair:{ordered}".encode("utf-8")


class StatePayloadEncryptor:
    """Encrypt/decrypt State.payload with ChaCha20-Poly1305 + HKDF-SHA256."""

    ALGORITHM = "ChaCha20-Poly1305+HKDF-SHA256"
    VERSION = 1

    def __init__(
        self,
        master_pairing_key: bytes,
        *,
        fleet_salt: bytes,
        key_context: bytes | None = None,
        local_device_id: str | None = None,
        peer_device_id: str | None = None,
    ) -> None:
        if len(master_pairing_key) < 32:
            raise ValueError("master_pairing_key must contain at least 256 bits")
        if len(fleet_salt) < 16:
            raise ValueError("fleet_salt must contain at least 128 bits")

        if key_context is None:
            key_context = _pair_context(local_device_id, peer_device_id)
        if not isinstance(key_context, (bytes, bytearray)):
            raise TypeError("key_context must be bytes")

        self._local_device_id = local_device_id
        self._peer_device_id = peer_device_id
        self._key = HKDF(
            algorithm=hashes.SHA256(),
            length=_KEY_SIZE,
            salt=fleet_salt,
            info=b"eiraos-fleet-sync-v1\x00" + bytes(key_context),
        ).derive(master_pairing_key)
        self._aead = ChaCha20Poly1305(self._key)
        self._used_nonces: set[bytes] = set()
        self._nonce_lock = threading.Lock()

    @staticmethod
    def generate_master_key() -> bytes:
        return os.urandom(32)

    @staticmethod
    def generate_fleet_salt() -> bytes:
        return os.urandom(16)

    @staticmethod
    def _metadata(state: State) -> dict[str, Any]:
        return {
            "id": str(state.id),
            "version": state.version,
            "hash": state.hash,
            "previous_state_id": (
                str(state.previous_state_id) if state.previous_state_id else None
            ),
        }

    def _reserve_nonce(self, nonce: bytes | None = None) -> bytes:
        """Return a unique nonce for this derived key; never reuse."""
        with self._nonce_lock:
            if nonce is not None:
                if len(nonce) != _NONCE_SIZE:
                    raise ValueError(f"nonce must be {_NONCE_SIZE} bytes")
                if nonce in self._used_nonces:
                    raise NonceReuseError("nonce must not be reused with the same key")
                self._used_nonces.add(nonce)
                return nonce

            for _ in range(_MAX_NONCE_RETRIES):
                candidate = os.urandom(_NONCE_SIZE)
                if candidate not in self._used_nonces:
                    self._used_nonces.add(candidate)
                    return candidate
            raise NonceReuseError("unable to allocate a unique nonce")

    def encrypt_state(
        self, state: State, *, nonce: bytes | None = None
    ) -> dict[str, Any]:
        """Encrypt state payload; leave Merkle metadata in cleartext header.

        ``nonce`` is only for tests that assert reuse is rejected. Production
        callers must omit it so a fresh random nonce is allocated.
        """
        if not isinstance(state.payload, dict) or not state.payload:
            raise PayloadIntegrityError("state payload must be a non-empty object")

        metadata = self._metadata(state)
        protected_header = {
            "algorithm": self.ALGORITHM,
            "envelope_version": self.VERSION,
            "metadata": metadata,
        }
        plaintext = _canonical_json(
            {
                "timestamp_ns": state.timestamp_ns,
                "type": state.type,
                "payload": state.payload,
            }
        )
        allocated = self._reserve_nonce(nonce)
        ciphertext = self._aead.encrypt(
            allocated, plaintext, _canonical_json(protected_header)
        )
        return {
            **protected_header,
            "nonce": base64.b64encode(allocated).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }

    def decrypt_state(self, envelope: Mapping[str, Any]) -> State:
        """Decrypt and authenticate an envelope produced by ``encrypt_state``."""
        if not isinstance(envelope, Mapping):
            raise PayloadIntegrityError("envelope must be an object")
        try:
            if "ciphertext" not in envelope or envelope.get("ciphertext") in (None, ""):
                raise PayloadIntegrityError("ciphertext is required")
            if "nonce" not in envelope or envelope.get("nonce") in (None, ""):
                raise PayloadIntegrityError("nonce is required")

            protected_header = {
                "algorithm": envelope["algorithm"],
                "envelope_version": int(envelope["envelope_version"]),
                "metadata": dict(envelope["metadata"]),
            }
            if protected_header["algorithm"] != self.ALGORITHM:
                raise PayloadIntegrityError("Unsupported encryption algorithm")
            if protected_header["envelope_version"] != self.VERSION:
                raise PayloadIntegrityError("Unsupported envelope version")

            nonce = base64.b64decode(str(envelope["nonce"]), validate=True)
            ciphertext = base64.b64decode(str(envelope["ciphertext"]), validate=True)
            plaintext = self._aead.decrypt(
                nonce, ciphertext, _canonical_json(protected_header)
            )
            protected = json.loads(plaintext)
            if not isinstance(protected, dict):
                raise PayloadIntegrityError("decrypted body must be an object")

            payload = protected.get("payload")
            if not isinstance(payload, dict) or not payload:
                raise PayloadIntegrityError("decrypted payload is missing or empty")

            metadata = protected_header["metadata"]
            state = State(
                id=UUID(str(metadata["id"])),
                version=int(metadata["version"]),
                hash=str(metadata["hash"]),
                previous_state_id=(
                    UUID(str(metadata["previous_state_id"]))
                    if metadata.get("previous_state_id")
                    else None
                ),
                timestamp_ns=int(protected["timestamp_ns"]),
                type=str(protected["type"]),
                payload=dict(payload),
            )
        except PayloadIntegrityError:
            raise
        except (InvalidTag, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise PayloadIntegrityError(
                "Encrypted state authentication failed"
            ) from exc

        if not state.is_hash_valid():
            raise PayloadIntegrityError("Decrypted state hash is invalid")
        return state
