"""Tenant root and operational keys (EIRA-RIGHTS-SET-1.3 §3.1).

Two levels, so a leaked signing key can be withdrawn without touching the
device:

- **Root keys** are pinned at enroll (`rights_roots` in enrollment). Kept
  offline by the tenant (HSM). A root never signs a rights set; it only
  certifies operational keys and signs the revocation list.
- **Operational keys** sign rights sets. Each has a certificate signed by a
  root, bound to the tenant, valid for at most MAX_KEY_LIFETIME.
- **Revocation list**: signed by a root, `sequence` only goes up. A key on it
  is no longer an anchor, and a cached set it signed loses its rights.

`operational_anchors` turns certificates + revocations into the anchors that
`contract.verify` takes, so set verification itself is unchanged. Pure
functions; no I/O, no clock.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.rights import contract

CERT_DOMAIN = b"EIRAOS-RIGHTS-KEY-V1"
REVOCATION_DOMAIN = b"EIRAOS-RIGHTS-REVOKE-V1"
MAX_KEY_LIFETIME = timedelta(days=90)
MAX_REVOKED = 4096
_TIME = "%Y-%m-%dT%H:%M:%SZ"


class KeyReason:
    MALFORMED = "malformed"
    UNKNOWN_ROOT = "unknown_root"
    ROOT_EXPIRED = "root_expired"
    BAD_SIGNATURE = "bad_signature"
    WRONG_TENANT = "wrong_tenant"
    LIFETIME_OVER_CAP = "lifetime_over_cap"
    NOT_YET_VALID = "not_yet_valid"
    EXPIRED = "expired"
    SEQUENCE_ROLLBACK = "sequence_rollback"
    SEQUENCE_CONFLICT = "sequence_conflict"


class KeyRejected(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Root:
    public_key: bytes
    not_after: datetime


@dataclass(frozen=True)
class KeyCertificate:
    key_id: str
    public_key: bytes
    tenant_id: str
    not_before: datetime
    not_after: datetime
    issuer: str


@dataclass(frozen=True)
class Revocations:
    tenant_id: str
    sequence: int
    revoked: frozenset[str]
    digest: str


def _ts(text: Any) -> datetime:
    if not isinstance(text, str):
        raise KeyRejected(KeyReason.MALFORMED)
    try:
        return datetime.strptime(text, _TIME).replace(tzinfo=timezone.utc)
    except ValueError:
        raise KeyRejected(KeyReason.MALFORMED) from None


def _id(value: Any) -> str:
    if not isinstance(value, str) or not 0 < len(value) <= 128 or not value.isascii():
        raise KeyRejected(KeyReason.MALFORMED)
    return value


def _signing_input(domain: bytes, doc: Mapping[str, Any]) -> bytes:
    unsigned = dict(doc)
    unsigned["signature"] = {k: v for k, v in doc["signature"].items() if k != "value"}
    return bytes([len(domain)]) + domain + contract.canonical(unsigned)


def _parse(raw: bytes, marker: str, fields: set[str]) -> dict[str, Any]:
    try:
        doc = contract.parse(raw)
    except contract._Reject:
        raise KeyRejected(KeyReason.MALFORMED) from None
    if doc.get(marker) != "1" or set(doc) != fields | {marker, "signature"}:
        raise KeyRejected(KeyReason.MALFORMED)
    sig = doc["signature"]
    if not isinstance(sig, dict) or set(sig) != {"alg", "key_id", "value"} or sig["alg"] != "ed25519":
        raise KeyRejected(KeyReason.MALFORMED)
    return doc


def _check_root(doc: Mapping[str, Any], domain: bytes, roots: Mapping[str, Root], now: datetime) -> str:
    issuer = _id(doc["signature"]["key_id"])
    root = roots.get(issuer)
    if root is None:
        raise KeyRejected(KeyReason.UNKNOWN_ROOT)
    if now >= root.not_after:
        raise KeyRejected(KeyReason.ROOT_EXPIRED)
    try:
        signature = contract._b64url(doc["signature"]["value"])
        Ed25519PublicKey.from_public_bytes(root.public_key).verify(signature, _signing_input(domain, doc))
    except (InvalidSignature, ValueError, TypeError):
        raise KeyRejected(KeyReason.BAD_SIGNATURE) from None
    return issuer


def signing_input_certificate(doc: Mapping[str, Any]) -> bytes:
    return _signing_input(CERT_DOMAIN, doc)


def signing_input_revocations(doc: Mapping[str, Any]) -> bytes:
    return _signing_input(REVOCATION_DOMAIN, doc)


def verify_certificate(
    raw: bytes, *, roots: Mapping[str, Root], tenant_id: str, now: datetime, allow_expired: bool = False
) -> KeyCertificate:
    doc = _parse(raw, "eira_rights_key", {"key_id", "public_key", "tenant_id", "not_before", "not_after"})
    issuer = _check_root(doc, CERT_DOMAIN, roots, now)
    key_id = _id(doc["key_id"])
    if key_id in roots:
        raise KeyRejected(KeyReason.MALFORMED)  # a root is never an operational key
    try:
        public = contract._b64url(doc["public_key"])
    except (ValueError, TypeError):
        raise KeyRejected(KeyReason.MALFORMED) from None
    if len(public) != 32:
        raise KeyRejected(KeyReason.MALFORMED)
    if doc["tenant_id"] != tenant_id:
        raise KeyRejected(KeyReason.WRONG_TENANT)
    not_before, not_after = _ts(doc["not_before"]), _ts(doc["not_after"])
    if not_after <= not_before or not_after - not_before > MAX_KEY_LIFETIME:
        raise KeyRejected(KeyReason.LIFETIME_OVER_CAP)
    if now + contract.CLOCK_SKEW < not_before:
        raise KeyRejected(KeyReason.NOT_YET_VALID)
    if now >= not_after and not allow_expired:
        raise KeyRejected(KeyReason.EXPIRED)
    return KeyCertificate(key_id, public, tenant_id, not_before, not_after, issuer)


def verify_revocations(
    raw: bytes,
    *,
    roots: Mapping[str, Root],
    tenant_id: str,
    now: datetime,
    previous: Revocations | None,
) -> Revocations:
    """The newer list replaces the older; it must contain every key the older
    one revoked (revocation is permanent) and a higher sequence."""
    doc = _parse(raw, "eira_rights_revocations", {"tenant_id", "sequence", "issued_at", "revoked"})
    _check_root(doc, REVOCATION_DOMAIN, roots, now)
    if doc["tenant_id"] != tenant_id:
        raise KeyRejected(KeyReason.WRONG_TENANT)
    sequence = doc["sequence"]
    revoked = doc["revoked"]
    if (
        not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1
        or not isinstance(revoked, list) or len(revoked) > MAX_REVOKED
    ):
        raise KeyRejected(KeyReason.MALFORMED)
    if now + contract.CLOCK_SKEW < _ts(doc["issued_at"]):
        raise KeyRejected(KeyReason.NOT_YET_VALID)
    ids = frozenset(_id(k) for k in revoked)
    digest = "sha256:" + hashlib.sha256(signing_input_revocations(doc)).hexdigest()
    if previous is not None:
        if sequence < previous.sequence:
            raise KeyRejected(KeyReason.SEQUENCE_ROLLBACK)
        if sequence == previous.sequence and digest != previous.digest:
            raise KeyRejected(KeyReason.SEQUENCE_CONFLICT)
        if not previous.revoked <= ids:
            raise KeyRejected(KeyReason.SEQUENCE_ROLLBACK)  # un-revoking is not possible
    return Revocations(tenant_id, sequence, ids, digest)


def operational_anchors(
    certificates: Iterable[bytes],
    *,
    roots: Mapping[str, Root],
    tenant_id: str,
    revocations: Revocations | None,
    now: datetime,
) -> dict[str, contract.Anchor]:
    """Anchors for `contract.verify`. Invalid certificates are skipped (a set
    signed by such a key is then `unknown_key_id`); revoked keys stay, marked,
    so the set is rejected as `key_revoked`."""
    revoked = revocations.revoked if revocations else frozenset()
    anchors: dict[str, contract.Anchor] = {}
    for raw in certificates:
        try:
            # An expired but otherwise valid certificate stays an anchor with
            # its not_after, so a set it signed is rejected as anchor_expired
            # rather than as an unknown key.
            cert = verify_certificate(raw, roots=roots, tenant_id=tenant_id, now=now, allow_expired=True)
        except KeyRejected:
            continue
        anchors[cert.key_id] = contract.Anchor(
            "managed", cert.public_key, not_after=cert.not_after, revoked=cert.key_id in revoked
        )
    return anchors
