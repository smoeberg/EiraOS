"""Paired devices and how they prove who they are (UDVIKLINGSPLAN F1c.1).

A device enrolls with two public keys: an X25519 key for the encrypted state
payloads and an Ed25519 key that signs. Its id is the fingerprint of the
signing key. Enrollment carries a proof that the device holds that key (a
signature over the pairing code and both keys).

Every synchronization call is signed: the device asks for a challenge (a
random nonce, single use, valid CHALLENGE_TTL_SECONDS), and signs the method,
its id, the nonce and the call's parameters (``sync_message``). The registry
checks the signature with the enrolled key, then consumes the nonce. There is
no bearer token: one that leaked could be replayed for ever, and a signature
over one nonce cannot be used for another call (vurderingen G-1).

A device enrolled before F1c.1 has no signing key and cannot synchronize
until it enrolls again.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey

# How long a challenge may be answered, and how many a device may hold.
CHALLENGE_TTL_SECONDS = 60
MAX_OPEN_CHALLENGES = 16
ENROLL_CONTEXT = "eira-fleet-enroll-v1"
SYNC_CONTEXT = "eira-fleet-sync-v1"
# Not part of the signed parameters: the proof itself, and keys the transport
# adds or strips ("_eira" is the IPC token, "_peer" the kernel's caller).
UNSIGNED_FIELDS = frozenset({"device_id", "nonce", "signature"})


def canonical_json(value: Any) -> bytes:
    """The bytes a device signs: sorted keys, no spaces, UTF-8, no floats'
    surprises (NaN and Infinity are refused)."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def enroll_message(pairing_code: str, public_key: str, signing_key: str) -> bytes:
    return canonical_json({
        "v": ENROLL_CONTEXT,
        "pairing_code_sha256": hashlib.sha256(pairing_code.encode("ascii")).hexdigest(),
        "public_key": public_key,
        "signing_key": signing_key,
    })


def signed_params(params: Any) -> dict[str, Any]:
    return {
        str(key): value for key, value in dict(params).items()
        if key not in UNSIGNED_FIELDS and not str(key).startswith("_")
    }


def sync_message(method: str, device_id: str, nonce: str, params: Any) -> bytes:
    return canonical_json({
        "v": SYNC_CONTEXT,
        "method": method,
        "device_id": device_id,
        "nonce": nonce,
        "params": signed_params(params),
    })


def _ed25519_key(signing_key: str) -> Ed25519PublicKey:
    try:
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(signing_key, validate=True))
    except (ValueError, TypeError) as exc:
        raise ValueError("signing_key must be a base64-encoded Ed25519 key") from exc


def _verify(signing_key: str, signature: Any, message: bytes) -> bool:
    try:
        raw = base64.b64decode(str(signature), validate=True)
        _ed25519_key(signing_key).verify(raw, message)
    except (ValueError, TypeError, InvalidSignature):
        return False
    return True


def device_fingerprint(public_key: str) -> str:
    """The device's identity: SHA-256 of its raw public key, in hex.

    EIRA-CONTEXT §1 defines ``device_id`` as a fingerprint of the device's key,
    never a name the device picks. Since F1c.1 it is taken of the Ed25519
    signing key, the key the device proves itself with.
    """
    raw = base64.b64decode(public_key, validate=True)
    return hashlib.sha256(raw).hexdigest()


class DeviceAuthorizationError(PermissionError):
    """Raised when an unknown or revoked device attempts fleet access."""


@dataclass(frozen=True)
class PairedDevice:
    device_id: str
    name: str
    os_type: str
    public_key: str
    status: str
    paired_at: str
    last_heartbeat: str | None
    signing_key: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class DeviceRegistry:
    def __init__(
        self, db_path: str = ":memory:", heartbeat_ttl_seconds: int = 300
    ) -> None:
        if heartbeat_ttl_seconds <= 0:
            raise ValueError("heartbeat_ttl_seconds must be positive")
        self.db_path = db_path
        self.heartbeat_ttl_seconds = heartbeat_ttl_seconds
        self._lock = threading.RLock()
        self._shared: sqlite3.Connection | None = None
        if db_path == ":memory:":
            self._shared = sqlite3.connect(":memory:", check_same_thread=False)
            self._shared.row_factory = sqlite3.Row
        else:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @staticmethod
    def _now() -> str:
        # SQLite's strftime() cannot parse ISO 8601 with "T" and a UTC
        # offset suffix; it returns NULL and expiry comparisons silently
        # never match (fail-open). Store timestamps in SQLite's native
        # format instead: "YYYY-MM-DD HH:MM:SS" (UTC).
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def _connect(self) -> sqlite3.Connection:
        if self._shared is not None:
            return self._shared
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._lock:
            connection = self._connect()
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pairing_codes (
                    code_hash TEXT PRIMARY KEY,
                    expires_at INTEGER NOT NULL,
                    consumed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS fleet_devices (
                    device_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    os_type TEXT NOT NULL,
                    public_key TEXT UNIQUE NOT NULL,
                    auth_token_hash TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    paired_at TEXT NOT NULL,
                    last_heartbeat TEXT
                );
                CREATE TABLE IF NOT EXISTS fleet_challenges (
                    nonce TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    used_at TEXT
                );
                """
            )
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(fleet_devices)"
                ).fetchall()
            }
            if "auth_token_hash" not in columns:
                connection.execute(
                    """
                    ALTER TABLE fleet_devices
                    ADD COLUMN auth_token_hash TEXT NOT NULL DEFAULT ''
                    """
                )
            if "signing_key" not in columns:
                connection.execute("ALTER TABLE fleet_devices ADD COLUMN signing_key TEXT")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS fleet_devices_signing_key "
                "ON fleet_devices(signing_key) WHERE signing_key IS NOT NULL"
            )
            # No bearer tokens any more (F1c.1): forget the old ones.
            connection.execute("UPDATE fleet_devices SET auth_token_hash = '' WHERE auth_token_hash != ''")
            connection.commit()
            if self._shared is None:
                connection.close()

    def create_pairing_token(self, ttl_seconds: int = 300) -> dict[str, Any]:
        if not 30 <= ttl_seconds <= 3600:
            raise ValueError("Pairing token lifetime must be between 30 and 3600 seconds")
        code = secrets.token_urlsafe(24)
        digest = hashlib.sha256(code.encode("ascii")).hexdigest()
        expires_at = int(time.time()) + ttl_seconds
        with self._lock:
            connection = self._connect()
            connection.execute(
                "INSERT INTO pairing_codes(code_hash, expires_at) VALUES (?, ?)",
                (digest, expires_at),
            )
            connection.commit()
            if self._shared is None:
                connection.close()
        qr_payload = code
        return {"code": code, "expires_at": expires_at, "qr_payload": qr_payload}

    @staticmethod
    def _validate_public_key(public_key: str) -> None:
        try:
            raw = base64.b64decode(public_key, validate=True)
            X25519PublicKey.from_public_bytes(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError("public_key must be a base64-encoded X25519 key") from exc

    def enroll(
        self,
        *,
        pairing_code: str,
        name: str,
        os_type: str,
        public_key: str,
        signing_key: str,
        proof: str,
        device_id: str | None = None,
    ) -> PairedDevice:
        if not name:
            raise ValueError("name is required")
        if os_type.casefold() not in {"ubuntu", "android"}:
            raise ValueError("os_type must be ubuntu or android")
        os_type = os_type.casefold()
        self._validate_public_key(public_key)
        _ed25519_key(signing_key)
        # The device holds the signing key: it signed the pairing code and
        # both keys. A copied public key cannot be enrolled by someone else.
        if not _verify(signing_key, proof, enroll_message(pairing_code, public_key, signing_key)):
            raise DeviceAuthorizationError("Enrollment proof does not verify")
        # The id is derived from the key, never chosen by the caller: a caller
        # cannot claim another device's id or keep an id with a new key.
        fingerprint = device_fingerprint(signing_key)
        if device_id is not None and device_id != fingerprint:
            raise DeviceAuthorizationError(
                "device_id must be the fingerprint of signing_key"
            )
        device_id = fingerprint
        digest = hashlib.sha256(pairing_code.encode("ascii")).hexdigest()
        now = self._now()
        with self._lock:
            connection = self._connect()
            row = connection.execute(
                "SELECT * FROM pairing_codes WHERE code_hash = ?", (digest,)
            ).fetchone()
            if (
                row is None
                or row["consumed_at"] is not None
                or int(row["expires_at"]) < int(time.time())
            ):
                if self._shared is None:
                    connection.close()
                raise DeviceAuthorizationError("Pairing code is invalid, used, or expired")
            # Checked before the code is consumed, so a refused enrollment
            # does not burn the administrator's code.
            if connection.execute(
                "SELECT 1 FROM fleet_devices WHERE device_id = ? OR public_key = ? OR signing_key = ?",
                (device_id, public_key, signing_key),
            ).fetchone():
                if self._shared is None:
                    connection.close()
                raise DeviceAuthorizationError("Device is already enrolled")
            updated = connection.execute(
                """
                UPDATE pairing_codes SET consumed_at = ?
                WHERE code_hash = ? AND consumed_at IS NULL
                """,
                (now, digest),
            )
            if updated.rowcount != 1:
                if self._shared is None:
                    connection.close()
                raise DeviceAuthorizationError("Pairing code was already consumed")
            connection.execute(
                """
                INSERT INTO fleet_devices
                (device_id, name, os_type, public_key, signing_key, status, paired_at)
                VALUES (?, ?, ?, ?, ?, 'active', ?)
                """,
                (device_id, name, os_type, public_key, signing_key, now),
            )
            connection.commit()
            if self._shared is None:
                connection.close()
        return self.get(device_id)

    def get(self, device_id: str) -> PairedDevice:
        with self._lock:
            connection = self._connect()
            row = connection.execute(
                """
                SELECT device_id, name, os_type, public_key, status,
                       paired_at, last_heartbeat, signing_key
                FROM fleet_devices WHERE device_id = ?
                """,
                (device_id,),
            ).fetchone()
            if self._shared is None:
                connection.close()
        if row is None:
            raise DeviceAuthorizationError("Device is not paired")
        return PairedDevice(**dict(row))

    def assert_authorized(
        self,
        device_id: str,
        *,
        public_key: str | None = None,
    ) -> PairedDevice:
        """The device is paired and active (and has this X25519 key, if
        given). Says nothing about who is asking: see verify_request."""
        self._expire_stale_devices()
        device = self.get(device_id)
        if device.status != "active":
            raise DeviceAuthorizationError(f"Device is {device.status}")
        if public_key is not None and not hmac.compare_digest(device.public_key, public_key):
            raise DeviceAuthorizationError("Device public key does not match registry")
        return device

    def _signing_device(self, device_id: str) -> PairedDevice:
        device = self.assert_authorized(device_id)
        if not device.signing_key:
            raise DeviceAuthorizationError(
                "Device was enrolled without a signing key; enroll it again"
            )
        return device

    def challenge(self, device_id: str) -> dict[str, Any]:
        """A single-use nonce for one signed call by this device."""
        self._signing_device(device_id)
        nonce = secrets.token_urlsafe(32)
        now = int(time.time())
        expires_at = now + CHALLENGE_TTL_SECONDS
        with self._lock:
            connection = self._connect()
            connection.execute(
                "DELETE FROM fleet_challenges WHERE expires_at < ? OR used_at IS NOT NULL", (now,)
            )
            (open_count,) = connection.execute(
                "SELECT COUNT(*) FROM fleet_challenges WHERE device_id = ?", (device_id,)
            ).fetchone()
            if open_count >= MAX_OPEN_CHALLENGES:
                connection.commit()
                if self._shared is None:
                    connection.close()
                raise DeviceAuthorizationError("Too many open challenges for this device")
            connection.execute(
                "INSERT INTO fleet_challenges(nonce, device_id, expires_at) VALUES (?, ?, ?)",
                (nonce, device_id, expires_at),
            )
            connection.commit()
            if self._shared is None:
                connection.close()
        return {"device_id": device_id, "nonce": nonce, "expires_at": expires_at}

    def verify_request(
        self,
        method: str,
        device_id: str,
        params: Any,
        *,
        public_key: str | None = None,
    ) -> PairedDevice:
        """The call is signed by the device's enrolled key over a challenge
        it was given, which is then used up. Any failure refuses."""
        device = self._signing_device(device_id)
        if public_key is not None and not hmac.compare_digest(device.public_key, public_key):
            raise DeviceAuthorizationError("Device public key does not match registry")
        nonce = params.get("nonce")
        signature = params.get("signature")
        if not isinstance(nonce, str) or not nonce or not isinstance(signature, str) or not signature:
            raise DeviceAuthorizationError("A signed challenge is required")
        try:
            message = sync_message(method, device_id, nonce, params)
        except (TypeError, ValueError) as exc:
            raise DeviceAuthorizationError("Parameters cannot be signed") from exc
        # The signature first: someone who only saw the nonce cannot use it up.
        if not _verify(str(device.signing_key), signature, message):
            raise DeviceAuthorizationError("Signature does not verify")
        with self._lock:
            connection = self._connect()
            used = connection.execute(
                """
                UPDATE fleet_challenges SET used_at = ?
                WHERE nonce = ? AND device_id = ? AND used_at IS NULL AND expires_at >= ?
                """,
                (self._now(), nonce, device_id, int(time.time())),
            )
            connection.commit()
            if self._shared is None:
                connection.close()
        if used.rowcount != 1:
            raise DeviceAuthorizationError("Challenge is unknown, used or expired")
        return device

    def heartbeat(self, device_id: str) -> PairedDevice:
        self.assert_authorized(device_id)
        with self._lock:
            connection = self._connect()
            connection.execute(
                "UPDATE fleet_devices SET last_heartbeat = ? WHERE device_id = ?",
                (self._now(), device_id),
            )
            connection.commit()
            if self._shared is None:
                connection.close()
        return self.get(device_id)

    def revoke(self, device_id: str) -> PairedDevice:
        with self._lock:
            connection = self._connect()
            updated = connection.execute(
                "UPDATE fleet_devices SET status = 'revoked' WHERE device_id = ?",
                (device_id,),
            )
            connection.commit()
            if self._shared is None:
                connection.close()
        if updated.rowcount != 1:
            raise DeviceAuthorizationError("Device is not paired")
        return self.get(device_id)

    def _expire_stale_devices(self) -> None:
        cutoff = time.time() - self.heartbeat_ttl_seconds
        with self._lock:
            connection = self._connect()
            connection.execute(
                "UPDATE fleet_devices SET status = 'expired' "
                "WHERE status = 'active' "
                "AND CAST(strftime('%s', COALESCE(last_heartbeat, paired_at)) AS INTEGER) < ?",
                (cutoff,),
            )
            connection.commit()
            if self._shared is None:
                connection.close()

    def list_active(self) -> list[PairedDevice]:
        self._expire_stale_devices()
        with self._lock:
            connection = self._connect()
            rows = connection.execute(
                """
                SELECT device_id, name, os_type, public_key, status,
                       paired_at, last_heartbeat, signing_key
                FROM fleet_devices WHERE status = 'active' ORDER BY device_id
                """
            ).fetchall()
            if self._shared is None:
                connection.close()
        return [PairedDevice(**dict(row)) for row in rows]

Device = PairedDevice
