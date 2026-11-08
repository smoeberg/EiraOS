"""EIRA Rights Set 1.0 — reference verifier (specs/EIRA-RIGHTS-SET-1.0.md).

This module *is* the executable contract. `eira-governance-agent` applies
sets with it, the gate evaluates them with it, and `eira-fleet-control` runs
the same vectors (tests/vectors/rights-set/) against its issuer in CI.

Pure functions only: no I/O, no clock. The caller supplies the effective time
(§4.1) so the contract cannot silently fall back to a wall clock the user can
set back.
"""

from __future__ import annotations

import base64
import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

import jsonschema
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Shipped with the package (debian/rules copies app/); one copy, no drift.
SCHEMA_PATH = Path(__file__).resolve().parent / "eira-rights-set-1.0.schema.json"
DOMAIN = b"EIRAOS-RIGHTS-V1"
MAX_BYTES = 1 << 20
# §4.2: compiled-in ceilings for expires_at - issued_at, per kind. Fleet
# chooses a managed TTL per tenant below its ceiling; the endpoint never
# raises either. The default set is renewed only by package updates, and on a
# private machine the owner has root, so its ceiling covers a support period.
MAX_TTL = {"managed": timedelta(days=30), "default": timedelta(days=400)}
CLOCK_SKEW = timedelta(minutes=5)


class Reason:
    """Stable rejection reasons. Reported verbatim in apply-result (§7)."""

    MALFORMED = "malformed"            # not JSON, duplicate key, float, > 1 MiB, non-NFC
    SCHEMA = "schema"                  # violates the JSON Schema
    UNKNOWN_KEY_ID = "unknown_key_id"
    WRONG_ANCHOR = "wrong_anchor"      # key exists but is not an anchor for this kind
    BAD_SIGNATURE = "bad_signature"
    WRONG_TENANT = "wrong_tenant"
    WRONG_DEVICE = "wrong_device"
    DEFAULT_ON_ENROLLED = "default_on_enrolled"
    TTL_OVER_CAP = "ttl_over_cap"
    NOT_YET_VALID = "not_yet_valid"
    EXPIRED = "expired"
    VERSION_ROLLBACK = "version_rollback"
    VERSION_CONFLICT = "version_conflict"  # same version, different content
    UNKNOWN_ACTION = "unknown_action"
    GRANT_OUTLIVES_SET = "grant_outlives_set"
    ANCHOR_EXPIRED = "anchor_expired"
    KEY_REVOKED = "key_revoked"


@dataclass(frozen=True)
class Anchor:
    kind: str                  # "managed" or "default"
    public_key: bytes          # raw 32-byte Ed25519 key
    # Managed anchors are operational keys certified by the tenant root
    # (app/rights/keys.py) and expire with their certificate. Judged on the
    # verifier's effective time, never on the set's issued_at: a leaked key
    # can backdate.
    not_after: datetime | None = None
    # Revoked by the root's revocation list (keys.py). Kept as an anchor so
    # the rejection says why, instead of "unknown key".
    revoked: bool = False


@dataclass(frozen=True)
class Device:
    enrolled: bool
    tenant_id: str = "unmanaged"
    device_id: str = "*"


@dataclass(frozen=True)
class Active:
    version: int
    content_hash: str
    tenant_id: str


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str | None = None
    noop: bool = False
    content_hash: str | None = None
    rights_set: dict[str, Any] | None = field(default=None, compare=False)


class _Reject(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# --- encoding ---------------------------------------------------------------


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise _Reject(Reason.MALFORMED)
        out[key] = value
    return out


def _reject_constant(_name: str) -> Any:
    raise _Reject(Reason.MALFORMED)  # NaN / Infinity


def parse(raw: bytes) -> dict[str, Any]:
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_BYTES:
        raise _Reject(Reason.MALFORMED)
    try:
        doc = json.loads(
            bytes(raw).decode("utf-8"),
            object_pairs_hook=_no_duplicates,
            parse_constant=_reject_constant,
            # §2 profile: no floats at all. JSON Schema treats 42.0 as an
            # integer, so this cannot be left to the schema.
            parse_float=_reject_constant,
        )
    except _Reject:
        raise
    except (UnicodeDecodeError, ValueError):
        raise _Reject(Reason.MALFORMED) from None
    if not isinstance(doc, dict):
        raise _Reject(Reason.MALFORMED)
    _require_nfc(doc)
    return doc


def _require_nfc(value: Any) -> None:
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            raise _Reject(Reason.MALFORMED)
    elif isinstance(value, dict):
        for key, item in value.items():
            if not key.isascii():
                raise _Reject(Reason.MALFORMED)
            _require_nfc(item)
    elif isinstance(value, list):
        for item in value:
            _require_nfc(item)


def canonical(doc: Mapping[str, Any]) -> bytes:
    """RFC 8785 for the profile in §2 (ASCII keys, integers, strings, bools)."""
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def signing_input(doc: Mapping[str, Any]) -> bytes:
    """§3: u8 len(DOMAIN) || DOMAIN || JCS(set with signature.value removed)."""
    unsigned = dict(doc)
    unsigned["signature"] = {k: v for k, v in doc["signature"].items() if k != "value"}
    return bytes([len(DOMAIN)]) + DOMAIN + canonical(unsigned)


def content_hash(doc: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(signing_input(doc)).hexdigest()


def _b64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _ts(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


@lru_cache(maxsize=1)
def _validator() -> jsonschema.Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def action_keys(registry: Iterable[str]) -> frozenset[str]:
    """Gate registry names → rights-set action keys (§2.2)."""
    return frozenset(n if n.startswith("system:") else f"edp:{n}" for n in registry)


# --- apply (§4) -------------------------------------------------------------


def verify(
    raw: bytes,
    *,
    anchors: Mapping[str, Anchor],
    device: Device,
    active: Active | None,
    now: datetime,
    registry: Iterable[str],
    max_ttl: Mapping[str, timedelta] = MAX_TTL,
) -> Verdict:
    """Decide whether a rights set may replace the active one. Fail closed."""
    try:
        doc = parse(raw)
        if not _validator().is_valid(doc):
            raise _Reject(Reason.SCHEMA)
        kind = doc["kind"]

        # §3 signature, before any field is trusted.
        anchor = anchors.get(doc["signature"]["key_id"])
        if anchor is None:
            raise _Reject(Reason.UNKNOWN_KEY_ID)
        if anchor.kind != kind:
            raise _Reject(Reason.WRONG_ANCHOR)
        if anchor.revoked:
            raise _Reject(Reason.KEY_REVOKED)
        if anchor.not_after is not None and now >= anchor.not_after:
            raise _Reject(Reason.ANCHOR_EXPIRED)
        try:
            Ed25519PublicKey.from_public_bytes(anchor.public_key).verify(
                _b64url(doc["signature"]["value"]), signing_input(doc)
            )
        except (InvalidSignature, ValueError):
            raise _Reject(Reason.BAD_SIGNATURE) from None

        # §4 rule 2: identity binding.
        if kind == "default":
            if device.enrolled:
                raise _Reject(Reason.DEFAULT_ON_ENROLLED)
        else:
            if not device.enrolled or doc["tenant_id"] != device.tenant_id:
                raise _Reject(Reason.WRONG_TENANT)
            if doc["device_id"] != device.device_id:
                raise _Reject(Reason.WRONG_DEVICE)

        # §4.2 lifetime ceiling and §4 rule 4 window (effective time, §4.1).
        issued, expires = _ts(doc["issued_at"]), _ts(doc["expires_at"])
        if expires <= issued or expires - issued > max_ttl[kind]:
            raise _Reject(Reason.TTL_OVER_CAP)
        if now + CLOCK_SKEW < issued:
            raise _Reject(Reason.NOT_YET_VALID)
        if now >= expires:
            raise _Reject(Reason.EXPIRED)
        for entry in (*doc["grants"], *doc["denies"]):
            if "expires_at" in entry and _ts(entry["expires_at"]) > expires:
                raise _Reject(Reason.GRANT_OUTLIVES_SET)

        # §4 rule 5: every key exists in the installed gate.
        known = action_keys(registry)
        for entry in (*doc["grants"], *doc["denies"]):
            if any(action not in known for action in entry["actions"]):
                raise _Reject(Reason.UNKNOWN_ACTION)

        # §4 rule 3: monotonic version per (tenant, device). A managed set
        # always supersedes the default set, whatever its number (§5).
        digest = content_hash(doc)
        if active is not None and active.tenant_id == doc["tenant_id"]:
            if doc["version"] < active.version:
                raise _Reject(Reason.VERSION_ROLLBACK)
            if doc["version"] == active.version:
                if digest != active.content_hash:
                    raise _Reject(Reason.VERSION_CONFLICT)
                return Verdict(ok=True, noop=True, content_hash=digest, rights_set=doc)
        elif active is not None and kind == "default":
            # active is managed (other tenant): no way back to default.
            raise _Reject(Reason.DEFAULT_ON_ENROLLED)
        return Verdict(ok=True, content_hash=digest, rights_set=doc)
    except _Reject as exc:
        return Verdict(ok=False, reason=exc.reason)


# --- evaluate (§6) ----------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str                       # "granted", "denied", "no_grant", "expired"
    grant_index: int | None = None
    required_assurance: str | None = None


def _subject_matches(subject: Mapping[str, Any], principal: str, groups: frozenset[str]) -> bool:
    if "principal" in subject:
        return subject["principal"] == principal
    if "group" in subject:
        return subject["group"] in groups
    return subject.get("authenticated") is True and bool(principal)


def _scope_matches(pattern: str, scope: str) -> bool:
    if pattern.endswith(":*"):
        return scope.startswith(pattern[:-1]) and scope != pattern[:-1]
    return pattern == scope


def _live(entry: Mapping[str, Any], now: datetime) -> bool:
    return "expires_at" not in entry or now < _ts(entry["expires_at"])


def authorize(
    rights_set: Mapping[str, Any] | None,
    *,
    principal: str,
    groups: Iterable[str],
    scope: str,
    action: str,
    now: datetime,
) -> Decision:
    """Layer 6 against one verified set. Called at every decision (§6)."""
    if rights_set is None or now >= _ts(rights_set["expires_at"]):
        return Decision(False, "expired")
    member = frozenset(groups)
    for entry in rights_set["denies"]:
        if (
            _live(entry, now)
            and action in entry["actions"]
            and _scope_matches(entry["scope"], scope)
            and _subject_matches(entry["subject"], principal, member)
        ):
            return Decision(False, "denied")
    for index, entry in enumerate(rights_set["grants"]):
        if (
            _live(entry, now)
            and action in entry["actions"]
            and _scope_matches(entry["scope"], scope)
            and _subject_matches(entry["subject"], principal, member)
        ):
            return Decision(True, "granted", index, entry.get("required_assurance"))
    return Decision(False, "no_grant")


def stricter_assurance(policy: str, grant: str | None) -> str:
    """§2.2: a grant can raise the policy's requirement, never lower it."""
    from app.gate.policy import ASSURANCE_RANK

    if grant is None:
        return policy
    return max(policy, grant, key=lambda level: ASSURANCE_RANK[level])
