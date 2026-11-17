"""A paired device in tests: what a real client does (UDVIKLINGSPLAN F1c.1).

It has an X25519 key (payloads) and an Ed25519 key (it signs). It enrolls
with a proof over the pairing code and both keys, and signs each sync call
over a challenge the registry gave it.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.fleet.device_registry import device_fingerprint, enroll_message, sync_message


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


@dataclass
class FleetTestDevice:
    name: str = "Phone"
    os_type: str = "ubuntu"
    _signing: Ed25519PrivateKey = field(default_factory=Ed25519PrivateKey.generate)
    _box: X25519PrivateKey = field(default_factory=X25519PrivateKey.generate)

    @property
    def public_key(self) -> str:
        return _b64(self._box.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))

    @property
    def signing_key(self) -> str:
        return _b64(self._signing.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))

    @property
    def device_id(self) -> str:
        return device_fingerprint(self.signing_key)

    def sign(self, message: bytes) -> str:
        return _b64(self._signing.sign(message))

    def enrollment(self, pairing_code: str) -> dict[str, Any]:
        return {
            "pairing_code": pairing_code,
            "name": self.name,
            "os_type": self.os_type,
            "public_key": self.public_key,
            "signing_key": self.signing_key,
            "proof": self.sign(enroll_message(pairing_code, self.public_key, self.signing_key)),
        }

    def enroll(self, registry: Any, pairing_code: str | None = None) -> Any:
        code = pairing_code or registry.create_pairing_token(300)["code"]
        return registry.enroll(**self.enrollment(code))

    def signed(self, registry: Any, method: str, params: dict[str, Any] | None = None,
               *, nonce: str | None = None) -> dict[str, Any]:
        """``params`` with device_id, a fresh challenge and the signature."""
        body = dict(params or {})
        if nonce is None:
            nonce = registry.challenge(self.device_id)["nonce"]
        signature = self.sign(sync_message(method, self.device_id, nonce, body))
        return {**body, "device_id": self.device_id, "nonce": nonce, "signature": signature}
