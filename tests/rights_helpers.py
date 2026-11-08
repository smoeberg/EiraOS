"""Test-only Fleet: signs rights sets with a fixed TEST key and installs them
through `contract.verify` + `RightsCache.install`, the same path the
governance agent uses. Tests never write rights any other way."""

from __future__ import annotations

import base64
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.gate.policy import REGISTRY
from app.rights import contract
from app.rights.cache import RightsCache

_SEED = bytes([0x33] * 32)  # TEST KEY ONLY
KEY_ID = "test-fleet-1"
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
        self.cache = RightsCache(directory, **kwargs)
        self.clock = clock
        self.kind = kind
        self.version = 0
        self.grants: list[dict[str, Any]] = []
        self.denies: list[dict[str, Any]] = []
        self.ttl = timedelta(days=14)
        key = Ed25519PrivateKey.from_private_bytes(_SEED)
        self._key = key
        public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.anchors = {KEY_ID: contract.Anchor(kind=kind, public_key=public)}

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
        self.cache.install(raw, verdict, self.clock())
        return verdict
