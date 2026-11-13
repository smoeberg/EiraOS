"""Device identity and the signed device list (EIRA-CONTEXT §5.0, §6.1, §8).

``device_id`` is the SHA-256 fingerprint (lowercase hex) of the device's
public signing key in DER SubjectPublicKeyInfo form. Keys are ECDSA P-256.
In F2.1 a key can live in software; the TPM (F2.3) changes where the private
key lives, not this format.

``keys/devices.signed`` is JSON, readable without EiraOS:

    {"list": {"eira_devices": "1", "context_id": "ctx_…", "version": 3,
              "issued_at": "…",
              "devices": [{"device_id": "…", "public_key": "<base64 SPKI DER>",
                           "key_protection": "tpm" | "file"}]},
     "signer": "<device_id>" | "org",
     "signature": "<base64 DER ECDSA-P256-SHA256 over canonical JSON of list>"}

Canonical JSON: keys sorted, separators "," and ":", UTF-8, no whitespace.

Who may sign (M-1, T-M1-e): an organisation context's list is signed by the
organisation's key; a personal context's list by a device already on the
current list. The very first list of a personal context is accepted if it
is signed by a device on that list (trust on first use, at creation).
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

Audit = Callable[[str, dict[str, Any]], None]


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def public_der(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def device_id_of(key: ec.EllipticCurvePublicKey) -> str:
    return sha256(public_der(key)).hexdigest()


def sign(key: ec.EllipticCurvePrivateKey, data: bytes) -> bytes:
    return key.sign(data, ec.ECDSA(hashes.SHA256()))


def verify(key: ec.EllipticCurvePublicKey, signature: bytes, data: bytes) -> bool:
    try:
        key.verify(signature, data, ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False


def load_public(b64_der: str) -> ec.EllipticCurvePublicKey:
    key = serialization.load_der_public_key(base64.b64decode(b64_der))
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("device keys are ECDSA P-256")
    return key


@dataclass(frozen=True)
class DeviceList:
    context_id: str
    version: int
    keys: dict[str, ec.EllipticCurvePublicKey]

    def key_of(self, device_id: str) -> ec.EllipticCurvePublicKey | None:
        return self.keys.get(device_id)


def make_device_list(
    context_id: str,
    version: int,
    devices: list[tuple[ec.EllipticCurvePublicKey, str]],
    signer: ec.EllipticCurvePrivateKey,
    *,
    signer_is_org: bool = False,
    issued_at: str,
) -> bytes:
    body = {
        "eira_devices": "1",
        "context_id": context_id,
        "version": version,
        "issued_at": issued_at,
        "devices": [
            {"device_id": device_id_of(key), "public_key": base64.b64encode(public_der(key)).decode(),
             "key_protection": protection}
            for key, protection in devices
        ],
    }
    return canonical({
        "list": body,
        "signer": "org" if signer_is_org else device_id_of(signer.public_key()),
        "signature": base64.b64encode(sign(signer, canonical(body))).decode(),
    })


def accept_device_list(
    raw: bytes,
    *,
    context_id: str,
    current: DeviceList | None,
    org_key: ec.EllipticCurvePublicKey | None,
    audit: Audit,
) -> DeviceList | None:
    """The new list if a key with the right signed it, else the current one
    (which may be None). A rejected list is audited and changes nothing."""

    def reject(reason: str) -> DeviceList | None:
        audit("context.device_list_rejected", {"context_id": context_id, "reason": reason})
        return current

    try:
        envelope = json.loads(raw)
        body = envelope["list"]
        signature = base64.b64decode(envelope["signature"])
        signer_name = envelope["signer"]
        if body.get("eira_devices") != "1" or body.get("context_id") != context_id:
            return reject("wrong_context")
        version = int(body["version"])
        keys = {}
        for entry in body["devices"]:
            key = load_public(entry["public_key"])
            if device_id_of(key) != entry["device_id"]:
                return reject("device_id_is_not_the_key_fingerprint")
            keys[entry["device_id"]] = key
    except (KeyError, TypeError, ValueError):
        return reject("malformed")

    if current is not None and version <= current.version:
        return reject("not_newer")
    if org_key is not None:
        # An organisation's context: only the organisation signs its list.
        signer = org_key if signer_name == "org" else None
    elif current is not None:
        signer = current.key_of(signer_name)
    else:
        signer = keys.get(signer_name)  # first list of a personal context
    if signer is None:
        return reject("signer_without_right")
    if not verify(signer, signature, canonical(body)):
        return reject("bad_signature")
    return DeviceList(context_id=context_id, version=version, keys=keys)
