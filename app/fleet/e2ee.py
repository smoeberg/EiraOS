from __future__ import annotations

import base64
import json
import os
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.state import State


class PayloadIntegrityError(ValueError):
    """Raised when an encrypted state cannot be authenticated."""


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


class StatePayloadEncryptor:
    ALGORITHM = "ChaCha20-Poly1305+HKDF-SHA256"
    VERSION = 1

    def __init__(
        self,
        master_pairing_key: bytes,
        *,
        fleet_salt: bytes,
        key_context: bytes = b"state-payload",
    ) -> None:
        if len(master_pairing_key) < 32:
            raise ValueError("master_pairing_key must contain at least 256 bits")
        if len(fleet_salt) < 16:
            raise ValueError("fleet_salt must contain at least 128 bits")
        self._key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=fleet_salt,
            info=b"eiraos-fleet-sync-v1\x00" + key_context,
        ).derive(master_pairing_key)

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

    def encrypt_state(self, state: State) -> dict[str, Any]:
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
        nonce = os.urandom(12)
        ciphertext = ChaCha20Poly1305(self._key).encrypt(
            nonce, plaintext, _canonical_json(protected_header)
        )
        return {
            **protected_header,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }

    def decrypt_state(self, envelope: Mapping[str, Any]) -> State:
        try:
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
            ciphertext = base64.b64decode(
                str(envelope["ciphertext"]), validate=True
            )
            plaintext = ChaCha20Poly1305(self._key).decrypt(
                nonce, ciphertext, _canonical_json(protected_header)
            )
            protected = json.loads(plaintext)
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
                payload=dict(protected["payload"]),
            )
        except PayloadIntegrityError:
            raise
        except (InvalidTag, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise PayloadIntegrityError("Encrypted state authentication failed") from exc
        if not state.is_hash_valid():
            raise PayloadIntegrityError("Decrypted state hash is invalid")
        return state
