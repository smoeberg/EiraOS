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

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey


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

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class DeviceEnrollment:
    device: PairedDevice
    auth_token: str

    def as_dict(self) -> dict[str, Any]:
        return {**self.device.as_dict(), "auth_token": self.auth_token}


class DeviceRegistry:
    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
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
        return datetime.now(timezone.utc).isoformat()

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
                    auth_token_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    paired_at TEXT NOT NULL,
                    last_heartbeat TEXT
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
        qr_payload = json.dumps(
            {"protocol": "eira-pair-v1", "code": code, "expires_at": expires_at},
            separators=(",", ":"),
        )
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
        device_id: str,
        name: str,
        os_type: str,
        public_key: str,
    ) -> DeviceEnrollment:
        if not device_id or not name:
            raise ValueError("device_id and name are required")
        if os_type not in {"Ubuntu", "Android"}:
            raise ValueError("os_type must be Ubuntu or Android")
        self._validate_public_key(public_key)
        digest = hashlib.sha256(pairing_code.encode("ascii")).hexdigest()
        auth_token = secrets.token_urlsafe(32)
        auth_token_hash = hashlib.sha256(auth_token.encode("ascii")).hexdigest()
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
                (device_id, name, os_type, public_key, auth_token_hash, status, paired_at)
                VALUES (?, ?, ?, ?, ?, 'active', ?)
                """,
                (device_id, name, os_type, public_key, auth_token_hash, now),
            )
            connection.commit()
            if self._shared is None:
                connection.close()
        return DeviceEnrollment(self.get(device_id), auth_token)

    def get(self, device_id: str) -> PairedDevice:
        with self._lock:
            connection = self._connect()
            row = connection.execute(
                """
                SELECT device_id, name, os_type, public_key, status,
                       paired_at, last_heartbeat
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
        auth_token: str | None = None,
        require_token: bool = False,
    ) -> PairedDevice:
        device = self.get(device_id)
        if device.status != "active":
            raise DeviceAuthorizationError(f"Device is {device.status}")
        if public_key is not None and not hmac.compare_digest(device.public_key, public_key):
            raise DeviceAuthorizationError("Device public key does not match registry")
        if require_token:
            if not auth_token:
                raise DeviceAuthorizationError("Device authentication token is required")
            with self._lock:
                connection = self._connect()
                row = connection.execute(
                    "SELECT auth_token_hash FROM fleet_devices WHERE device_id = ?",
                    (device_id,),
                ).fetchone()
                if self._shared is None:
                    connection.close()
            supplied = hashlib.sha256(auth_token.encode("ascii")).hexdigest()
            if row is None or not hmac.compare_digest(row["auth_token_hash"], supplied):
                raise DeviceAuthorizationError("Device authentication token is invalid")
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

    def list_active(self) -> list[PairedDevice]:
        with self._lock:
            connection = self._connect()
            rows = connection.execute(
                """
                SELECT device_id, name, os_type, public_key, status,
                       paired_at, last_heartbeat
                FROM fleet_devices WHERE status = 'active' ORDER BY device_id
                """
            ).fetchall()
            if self._shared is None:
                connection.close()
        return [PairedDevice(**dict(row)) for row in rows]

Device = PairedDevice
