"""Test-only Fleet: signs rights sets with a fixed TEST key and installs them
through `contract.verify` + `RightsCache.install`, the same path the
governance agent uses. Tests never write rights any other way."""

from __future__ import annotations

import base64
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.gate.policy import REGISTRY
from app.rights import contract, keys
from app.rights.cache import RightsCache

_SEED = bytes([0x33] * 32)  # TEST KEY ONLY: operational key that signs sets
KEY_ID = "test-fleet-1"
_ROOT_SEED = bytes([0x55] * 32)  # TEST KEY ONLY: tenant root, certifies KEY_ID
ROOT_ID = "test-root-1"
DEVICE = contract.Device(enrolled=True, tenant_id="test-tenant", device_id="test-device")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _ts(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def all_actions() -> list[str]:
    return sorted(contract.action_keys(REGISTRY))


class TestFleet:
    __test__ = False  # not a pytest class

    def __init__(self, directory: Path, clock, *, boot_clock=None, kind: str = "managed"):
        kwargs = {"boot_clock": boot_clock} if boot_clock is not None else {}
        # A managed test device is enrolled for real: the gate weighs the set
        # against enrollment (cache.resolve). A default device has no file.
        self.enrollment_path = Path(directory).parent / f"{Path(directory).name}-enrollment.json"
        self.cache = RightsCache(directory, enrollment_path=self.enrollment_path, **kwargs)
        self.clock = clock
        self.kind = kind
        self.version = 0
        self.grants: list[dict[str, Any]] = []
        self.denies: list[dict[str, Any]] = []
        self.ttl = timedelta(days=14)
        key = Ed25519PrivateKey.from_private_bytes(_SEED)
        self._key = key
        self._root = Ed25519PrivateKey.from_private_bytes(_ROOT_SEED)
        self.public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.root_public = self._root.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.cert_not_after = clock() + timedelta(days=80)
        self.revoked: list[str] = []
        self.revocation_sequence = 0
        if kind == "managed":
            self.enrollment_path.write_text(json.dumps(self.enrollment()))

    @property
    def anchors(self) -> dict[str, contract.Anchor]:
        """What the device would trust right now for this fleet's sets."""
        if self.kind == "default":
            return {KEY_ID: contract.Anchor("default", self.public)}
        from app.rights.fleet_api import read_enrollment

        enrolled = read_enrollment(self.enrollment_path)
        return keys.operational_anchors(
            [self.certificate()], roots=enrolled.rights_roots, tenant_id=DEVICE.tenant_id,
            revocations=None if not self.revocation_sequence else keys.verify_revocations(
                self.revocations(), roots=enrolled.rights_roots, tenant_id=DEVICE.tenant_id,
                now=self.clock(), previous=None),
            now=self.clock(),
        )

    def enrollment(self) -> dict[str, Any]:
        return {
            "eira_enrollment": "2",
            "tenant_id": DEVICE.tenant_id,
            "device_id": DEVICE.device_id,
            "fleet_url": "https://fleet.test",
            "rights_roots": {
                ROOT_ID: {"public_key": _b64url(self.root_public), "not_after": "2036-01-01T00:00:00Z"}
            },
        }

    def certificate(self, *, key_id: str = KEY_ID, public: bytes | None = None,
                    not_before: datetime | None = None, not_after: datetime | None = None,
                    tenant_id: str | None = None, root=None) -> bytes:
        """A root-signed certificate for an operational key."""
        doc = {
            "eira_rights_key": "1",
            "key_id": key_id,
            "public_key": _b64url(public or self.public),
            "tenant_id": tenant_id or DEVICE.tenant_id,
            "not_before": _ts(not_before or self.clock() - timedelta(days=1)),
            "not_after": _ts(not_after or self.cert_not_after),
            "signature": {"alg": "ed25519", "key_id": ROOT_ID, "value": "A" * 86},
        }
        doc["signature"]["value"] = _b64url((root or self._root).sign(keys.signing_input_certificate(doc)))
        return contract.canonical(doc)

    def revocations(self) -> bytes:
        doc = {
            "eira_rights_revocations": "1",
            "tenant_id": DEVICE.tenant_id,
            "sequence": self.revocation_sequence,
            "issued_at": _ts(self.clock()),
            "revoked": sorted(self.revoked),
            "signature": {"alg": "ed25519", "key_id": ROOT_ID, "value": "A" * 86},
        }
        doc["signature"]["value"] = _b64url(self._root.sign(keys.signing_input_revocations(doc)))
        return contract.canonical(doc)

    def revoke(self, key_id: str = KEY_ID) -> "TestFleet":
        self.revoked.append(key_id)
        self.revocation_sequence += 1
        return self

    def key_material(self) -> tuple[list[bytes], bytes | None]:
        return [self.certificate()], self.revocations() if self.revocation_sequence else None

    def grant(self, scope: str, actions: Iterable[str] | None = None, *, principal=None, group=None,
              expires_at: datetime | None = None, required_assurance: str | None = None) -> "TestFleet":
        entry: dict[str, Any] = {
            "subject": {"principal": principal} if principal else {"group": group} if group
            else {"authenticated": True},
            "scope": scope,
            "actions": sorted(set(actions or all_actions())),
        }
        if expires_at is not None:
            entry["expires_at"] = _ts(expires_at)
        if required_assurance is not None:
            entry["required_assurance"] = required_assurance
        self.grants.append(entry)
        return self

    def deny(self, scope: str, actions: Iterable[str], *, principal=None, group=None) -> "TestFleet":
        self.denies.append({
            "subject": {"principal": principal} if principal else {"group": group},
            "scope": scope,
            "actions": sorted(set(actions)),
        })
        return self

    def revoke_all(self) -> "TestFleet":
        self.grants, self.denies = [], []
        return self

    def document(self) -> dict[str, Any]:
        now = self.clock()
        managed = self.kind == "managed"
        doc = {
            "eira_rights": "1",
            "rights_set_id": f"00000000-0000-7000-8000-{self.version:012x}",
            "kind": self.kind,
            "tenant_id": DEVICE.tenant_id if managed else "unmanaged",
            "device_id": DEVICE.device_id if managed else "*",
            "version": self.version,
            "issued_at": _ts(now),
            "expires_at": _ts(now + self.ttl),
            "template": {"id": "test", "version": "1"},
            "issued_by": {"api_call_id": f"test-{self.version}", "fleet": "fleet.test"},
            "grants": copy.deepcopy(self.grants),
            "denies": copy.deepcopy(self.denies),
            "signature": {"alg": "ed25519", "key_id": KEY_ID, "value": "A" * 86},
        }
        doc["signature"]["value"] = _b64url(self._key.sign(contract.signing_input(doc)))
        return doc

    def publish(self) -> contract.Verdict:
        """Sign the next version and install it exactly as the agent would."""
        self.version += 1
        raw = contract.canonical(self.document())
        device = DEVICE if self.kind == "managed" else contract.Device(enrolled=False)
        verdict = contract.verify(
            raw, anchors=self.anchors, device=device, active=self.cache.active_meta(),
            now=self.clock(), registry=REGISTRY,
        )
        assert verdict.ok, verdict.reason
        if self.kind == "managed":
            self.cache.store_key_material(*self.key_material())
        self.cache.install(raw, verdict, self.clock())
        return verdict
