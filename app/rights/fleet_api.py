"""Endpoint ↔ Fleet rights API (specs/EIRA-FLEET-RIGHTS-API-1.0.md).

eira-os defines this boundary; Fleet implements the server side against
specs/eira-fleet-rights-api-1.0.openapi.json. Nothing here knows how Fleet
works: the agent depends only on `FleetRightsClient`, and every answer from
Fleet is untrusted until `contract.verify` has accepted the set.

Transport (HTTPS, mTLS device certificate, Fleet URL pinning) and the enroll
flow are Fleet Agent Protocol v0.1 §2. This module adds only what rights need:

    GET  /v1/desired-state?rights_version=N   → DesiredRights
    POST /v1/report/apply-result               ← ApplyReport
    POST /v1/heartbeat (fields)                ← RightsHeartbeat
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from app.rights import contract
from app.rights.keys import Root

API_VERSION = "1"
ENROLLMENT_VERSION = "2"  # 2: rights_roots (root keys) replace rights_anchors
MAX_KEY_CERTIFICATES = 16
MAX_KEY_DOC_BYTES = 64 * 1024
MAX_SET_BYTES = contract.MAX_BYTES
# Unpadded base64url length of MAX_SET_BYTES; the OpenAPI maxLength is
# checked against this one constant.
MAX_ENCODED_LENGTH = (4 * MAX_SET_BYTES + 2) // 3
# Written by enroll (root, 0644). The one place this path is configured.
ENROLLMENT_PATH = Path(os.environ.get("EIRA_ENROLLMENT_FILE", "/etc/eira/enrollment.json"))


class FleetError(Exception):
    """Fleet could not be reached or answered outside this API. The agent
    keeps the active set; offline is a normal state (RIGHTS-SET §5.1)."""


class ProtocolViolation(FleetError):
    """Fleet answered, but not in the shape this API defines."""


# --- enrollment (written by enroll, read by the agent) -----------------------


@dataclass(frozen=True)
class Enrollment:
    """/etc/eira/enrollment.json, written once by enrollment (root, 0644).

    `rights_roots` are the tenant's root keys, received over mTLS at enroll,
    each with a `not_after`. A root never signs a rights set: it certifies the
    operational keys that do and signs the revocation list (keys.py). Roots
    never arrive inside a rights set or desired state, so neither a
    compromised set nor a compromised operational key can name the key it
    should be trusted under. Changing a root means re-enrolling.
    """

    tenant_id: str
    device_id: str
    fleet_url: str
    rights_roots: Mapping[str, Root]

    @property
    def device(self) -> contract.Device:
        return contract.Device(enrolled=True, tenant_id=self.tenant_id, device_id=self.device_id)


def parse_enrollment(data: Mapping[str, Any]) -> Enrollment:
    try:
        if data["eira_enrollment"] != ENROLLMENT_VERSION:
            raise ValueError("unsupported enrollment version")
        url = data["fleet_url"]
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError("fleet_url must be https")
        roots = {}
        for key_id, root in data["rights_roots"].items():
            raw = _b64url(root["public_key"])
            if len(raw) != 32:
                raise ValueError(f"root {key_id}: not an Ed25519 key")
            not_after = datetime.strptime(root["not_after"], "%Y-%m-%dT%H:%M:%SZ")
            roots[key_id] = Root(raw, not_after.replace(tzinfo=timezone.utc))
        if not roots:
            raise ValueError("no rights roots")
        return Enrollment(str(data["tenant_id"]), str(data["device_id"]), url, roots)
    except (KeyError, TypeError, AttributeError, binascii.Error, ValueError) as exc:
        raise ValueError(f"malformed enrollment: {exc}") from None


def read_enrollment(path: Path | None = None) -> Enrollment | None:
    """None = not enrolled. A file that exists but is malformed is an error
    (ValueError): the device must never silently fall back to unmanaged."""
    path = path if path is not None else ENROLLMENT_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"malformed enrollment: {exc}") from None
    return parse_enrollment(data)


# --- messages -----------------------------------------------------------------


@dataclass(frozen=True)
class DesiredRights:
    """The rights part of GET /v1/desired-state.

    Every document is the exact signed bytes, base64url on the wire, so no
    JSON parser between Fleet and the verifier can reorder, deduplicate or
    renormalise it.

    - `rights_set`: None = nothing newer than `rights_version`.
    - `rights_keys`: root-signed certificates of the tenant's operational
      keys, always the full current list.
    - `rights_revocations`: the root-signed revocation list, if any.
    """

    rights_set: bytes | None
    rights_keys: tuple[bytes, ...] = ()
    rights_revocations: bytes | None = None


@dataclass(frozen=True)
class ApplyReport:
    """POST /v1/report/apply-result for a rights set."""

    device_id: str
    rights_set_id: str | None
    version: int | None
    result: str  # "applied" | "noop" | "rejected"
    reason: str | None = None  # contract.Reason when rejected

    def to_json(self) -> dict[str, Any]:
        return {"kind": "rights_set", **asdict(self)}


@dataclass(frozen=True)
class RightsHeartbeat:
    """Fields added to POST /v1/heartbeat so Fleet can see devices whose
    rights are missing, expired, misconfigured or about to expire."""

    rights_state: str  # "active" | "expired" | "missing" | "misconfigured"
    rights_reason: str | None  # why, when not "active" (cache.RightsState)
    rights_version: int | None
    rights_expires_at: str | None
    clock_rollback: bool

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def parse_desired_state(body: Any) -> DesiredRights:
    """Validate Fleet's answer. Anything else is a ProtocolViolation; the
    documents inside are still unverified."""
    if not isinstance(body, dict):
        raise ProtocolViolation("desired-state is not an object")
    rights_set = _document(body.get("rights_set"), MAX_SET_BYTES, "rights_set")
    keys = body.get("rights_keys") or []
    if not isinstance(keys, list) or len(keys) > MAX_KEY_CERTIFICATES:
        raise ProtocolViolation(f"rights_keys must be a list of at most {MAX_KEY_CERTIFICATES}")
    certificates = tuple(_document(k, MAX_KEY_DOC_BYTES, "rights_keys[]") for k in keys)
    if any(c is None for c in certificates):
        raise ProtocolViolation("rights_keys[] must be strings")
    revocations = _document(body.get("rights_revocations"), MAX_KEY_DOC_BYTES, "rights_revocations")
    return DesiredRights(rights_set, certificates, revocations)  # type: ignore[arg-type]


def _document(encoded: Any, limit: int, name: str) -> bytes | None:
    if encoded is None:
        return None
    if not isinstance(encoded, str) or len(encoded) > (4 * limit + 2) // 3:
        raise ProtocolViolation(f"{name} must be a base64url string of at most {limit} bytes")
    try:
        raw = _b64url(encoded)
    except (binascii.Error, ValueError):
        raise ProtocolViolation(f"{name} is not base64url") from None
    # Canonical encoding only: one wire string per document, so nothing that
    # logs or deduplicates on the string can see one document as two.
    if encode_rights_set(raw) != encoded:
        raise ProtocolViolation(f"{name} is not canonical base64url")
    return raw


def encode_rights_set(raw: bytes) -> str:
    """For Fleet (and the reference server in tests)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64url(text: str) -> bytes:
    if any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in text):
        raise binascii.Error("not base64url")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# --- the client the agent depends on -----------------------------------------


class FleetRightsClient(Protocol):
    """Implemented over HTTPS + mTLS by the governance agent's transport.
    Methods raise FleetError when Fleet is unreachable or misbehaves."""

    def desired_rights(self, active_version: int | None) -> DesiredRights: ...

    def report_apply(self, report: ApplyReport) -> None: ...
