"""Rights-set apply for the endpoint (EIRA-RIGHTS-SET-1.0 §4, §5).

This is the apply half of `eira-governance-agent`:

- `apply_default`: the bundle's signed default set on an unmanaged device.
- `sync_once`: one round against Fleet through `FleetRightsClient`
  (specs/EIRA-FLEET-RIGHTS-API-1.0.md). The agent never depends on how Fleet
  works, only on that interface; the HTTPS/mTLS transport implements it.

    eira-rights-apply apply-default
    eira-rights-apply sync           (one round against Fleet, then heartbeat)

Exit codes: 0 applied, no-op or not applicable (enrolled device);
1 rejected (the active set is kept; the reason is logged); 2 bundle missing.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping

from app.rights import contract
from app.rights.cache import RightsCache
from app.rights.fleet_api import (
    ApplyReport,
    Enrollment,
    FleetError,
    FleetRightsClient,
    RightsHeartbeat,
    read_enrollment,
)

BUNDLE_DIR = Path(os.environ.get("EIRA_RIGHTS_BUNDLE_DIR", "/usr/lib/eira-os/rights"))


def load_anchors(path: Path) -> dict[str, contract.Anchor]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for key_id, anchor in data["anchors"].items():
        if anchor["kind"] not in {"managed", "default"}:
            raise ValueError(f"anchor {key_id}: unknown kind")
        raw = base64.urlsafe_b64decode(anchor["public_key"] + "=" * (-len(anchor["public_key"]) % 4))
        if len(raw) != 32:
            raise ValueError(f"anchor {key_id}: not an Ed25519 public key")
        out[key_id] = contract.Anchor(kind=anchor["kind"], public_key=raw)
    return out


def enrollment(path: Path | None = None) -> Enrollment | None:
    return read_enrollment(path)


def apply(
    raw: bytes,
    *,
    anchors: Mapping[str, contract.Anchor],
    device: contract.Device,
    cache: RightsCache,
    registry: Iterable[str],
    wall_now: datetime,
) -> contract.Verdict:
    """Verify against the active set and install atomically, or change nothing.

    If another set is activated between the check and the install, the set is
    judged again against that one (fundregister S-23): an older version is
    then a rollback and the same version with other content a conflict, so
    concurrent activations end on the highest version or are refused, never
    on whichever happened to write last."""
    from app.rights.cache import Superseded

    registry = tuple(registry)
    # Every Superseded means another set was installed, so this ends; the
    # bound only guards against a cache that keeps changing under us.
    for _ in range(32):
        # §4.1: never judge a set on a wall clock that went back past what
        # this device has already seen.
        high_water = cache.high_water()
        now = max(wall_now, high_water) if high_water else wall_now
        verdict = contract.verify(
            raw, anchors=anchors, device=device, active=cache.active_meta(), now=now, registry=registry
        )
        if not verdict.ok:
            return verdict
        try:
            cache.install(raw, verdict, wall_now)
        except Superseded:
            continue
        return verdict
    return contract.Verdict(ok=False, reason=contract.Reason.VERSION_CONFLICT)


def _log(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


def apply_default(bundle: Path = BUNDLE_DIR, cache: RightsCache | None = None) -> int:
    from app.gate.policy import REGISTRY

    try:
        raw = (bundle / "default.json").read_bytes()
        anchors = load_anchors(bundle / "anchors.json")
    except (OSError, ValueError, KeyError) as exc:
        _log("rights.apply", result="bundle_missing", error=str(exc))
        return 2
    try:
        enrolled = enrollment()
    except ValueError as exc:
        # A broken enrollment must not turn a managed device into a private one.
        _log("rights.apply", result="rejected", reason="enrollment_malformed", error=str(exc))
        return 1
    if enrolled is not None:
        _log("rights.apply", result="not_applicable", reason="device is enrolled; Fleet supplies the set")
        return 0
    verdict = apply(
        raw,
        anchors=anchors,
        device=contract.Device(enrolled=False),
        cache=cache or RightsCache(),
        registry=REGISTRY,
        wall_now=datetime.now(timezone.utc),
    )
    if not verdict.ok:
        _log("rights.apply", result="rejected", reason=verdict.reason)
        return 1
    doc = verdict.rights_set or {}
    _log(
        "rights.apply",
        result="noop" if verdict.noop else "applied",
        kind=doc.get("kind"),
        version=doc.get("version"),
        rights_set_id=doc.get("rights_set_id"),
        expires_at=doc.get("expires_at"),
    )
    return 0


def sync_once(
    client: FleetRightsClient,
    enrolled: Enrollment,
    cache: RightsCache,
    *,
    registry: Iterable[str],
    wall_now: datetime,
) -> str:
    """One round: ask Fleet for anything newer, verify, install, report.

    Returns "offline", "unchanged", "applied", "noop", "rejected" or
    "rejected_known". Fleet being unreachable or misbehaving never changes the
    active set (§5.1). A rejection is final for those exact bytes (API §3.2):
    the same set is never verified again, and only re-reported if the first
    report did not reach Fleet. Fleet resolves it by issuing a new version.
    """
    active = cache.active_meta()
    try:
        desired = client.desired_rights(active.version if active else None)
    except FleetError as exc:
        _log("rights.sync", result="offline", error=str(exc))
        return "offline"
    _update_key_material(desired, enrolled, cache, wall_now)
    if desired.rights_set is None:
        return "unchanged"
    digest = "sha256:" + hashlib.sha256(desired.rights_set).hexdigest()
    known = cache.rejection(digest)
    if known is not None:
        if not known["reported"]:
            report = ApplyReport(enrolled.device_id, None, None, "rejected", known["reason"])
            if _deliver(client, report):
                cache.remember_rejection(digest, known["reason"], reported=True)
        return "rejected_known"
    verdict = apply(
        desired.rights_set,
        anchors=cache.anchors(enrolled, _effective(cache, wall_now)),
        device=enrolled.device,
        cache=cache,
        registry=registry,
        wall_now=wall_now,
    )
    if verdict.ok:
        doc = verdict.rights_set or {}
        result = "noop" if verdict.noop else "applied"
        report = ApplyReport(enrolled.device_id, doc.get("rights_set_id"), doc.get("version"), result)
    else:
        # Fields of a rejected set are unverified: report only the reason.
        result = "rejected"
        report = ApplyReport(enrolled.device_id, None, None, result, verdict.reason)
    _log("rights.sync", **report.to_json())
    delivered = _deliver(client, report)
    if result == "rejected":
        cache.remember_rejection(digest, verdict.reason or "", reported=delivered)
    return result


def _effective(cache: RightsCache, wall_now: datetime) -> datetime:
    high_water = cache.high_water()
    return max(wall_now, high_water) if high_water else wall_now


def _update_key_material(desired, enrolled: Enrollment, cache: RightsCache, wall_now: datetime) -> None:
    """Keys first, so a set signed by a newly certified key verifies in the
    same round, and a revocation takes effect before any set is looked at.

    - Revocation list: kept only if it verifies against a root and is not
      older than the stored one (it can only grow). Otherwise the stored
      list stays.
    - Certificates: Fleet sends the full current list; it replaces the
      stored one. Invalid certificates are never anchors (keys.py), so a
      bad list can only remove trust, never add it.
    """
    from app.rights import keys

    now = _effective(cache, wall_now)
    stored_certs, stored_rev = cache.key_material()
    revocations = stored_rev
    if desired.rights_revocations is not None and desired.rights_revocations != stored_rev:
        previous = None
        if stored_rev is not None:
            try:
                previous = keys.verify_revocations(
                    stored_rev, roots=enrolled.rights_roots, tenant_id=enrolled.tenant_id,
                    now=now, previous=None,
                )
            except keys.KeyRejected:
                previous = None
        try:
            keys.verify_revocations(
                desired.rights_revocations, roots=enrolled.rights_roots,
                tenant_id=enrolled.tenant_id, now=now, previous=previous,
            )
            revocations = desired.rights_revocations
        except keys.KeyRejected as exc:
            _log("rights.keys", revocations="rejected", reason=exc.reason)
    certificates = list(desired.rights_keys) if desired.rights_keys else stored_certs
    if certificates != stored_certs or revocations != stored_rev:
        cache.store_key_material(certificates, revocations)


def _deliver(client: FleetRightsClient, report: ApplyReport) -> bool:
    try:
        client.report_apply(report)
        return True
    except FleetError as exc:
        _log("rights.sync", report="not_delivered", error=str(exc))
        return False


POLL_INTERVAL = timedelta(minutes=15)
MAX_BACKOFF = timedelta(hours=6)


def next_poll(outcome: str, consecutive_offline: int, rng: random.Random | None = None) -> timedelta:
    """When to ask Fleet again (API §4). Offline backs off exponentially to
    six hours; every delay gets ±20 % jitter so a fleet of devices that lost
    Fleet together does not return together. A rejected set does not make the
    agent ask more often."""
    rng = rng or random.Random()
    if outcome == "offline":
        base = min(POLL_INTERVAL * (2 ** max(0, consecutive_offline - 1)), MAX_BACKOFF)
    else:
        base = POLL_INTERVAL
    return base * rng.uniform(0.8, 1.2)


def audit_anchor_for_fleet() -> dict | None:
    """The gate's latest audit anchor (written by intentd), for Fleet to keep
    as an off-machine witness (GATE-KERNEL bilag A pkt. 2)."""
    from app.gate.audit_anchor import ANCHOR_FILE

    try:
        data = json.loads(ANCHOR_FILE.read_text(encoding="utf-8"))
        return {"seq": int(data["seq"]), "head": str(data["head"]), "at": data.get("at")}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def heartbeat_fields(cache: RightsCache, wall_now: datetime) -> RightsHeartbeat:
    """Same judgement as the gate's (cache.resolve), so Fleet sees exactly why
    a device has no rights: never enrolled, waiting, broken or expired."""
    resolved = cache.resolve(wall_now)
    rights = resolved.rights
    return RightsHeartbeat(
        resolved.state,
        resolved.reason,
        rights.version if rights else None,
        rights.rights_set["expires_at"] if rights else None,
        rights.clock_rollback if rights else False,
    )


SYNC_EXIT = {"applied": 0, "noop": 0, "unchanged": 0, "rejected": 1, "rejected_known": 1, "offline": 3}


def sync(client: FleetRightsClient | None = None, cache: RightsCache | None = None) -> int:
    """One round against the enrolled Fleet, then a heartbeat.
    Exit: 0 ok, 1 set rejected, 2 not enrolled / misconfigured, 3 offline."""
    from app.gate.policy import REGISTRY

    try:
        enrolled = enrollment()
    except ValueError as exc:
        _log("rights.sync", result="misconfigured", reason="enrollment_malformed", error=str(exc))
        return 2
    if enrolled is None:
        _log("rights.sync", result="not_enrolled")
        return 2
    cache = cache or RightsCache()
    now = datetime.now(timezone.utc)
    due = cache.sync_due(now)
    if not due:
        _log("rights.sync", result="not_due")  # backing off after Fleet was unreachable
        return 0
    if client is None:
        from app.rights.transport import HttpsFleetRightsClient

        try:
            client = HttpsFleetRightsClient(enrolled)
        except (OSError, ValueError) as exc:
            _log("rights.sync", result="misconfigured", reason="fleet_tls_files", error=str(exc))
            return 2
    outcome = sync_once(client, enrolled, cache, registry=REGISTRY, wall_now=now)
    cache.record_sync(outcome, now, next_poll)
    heartbeat = getattr(client, "heartbeat", None)
    if heartbeat is not None and outcome != "offline":
        from app.gate import audit_seal

        seal = audit_seal.for_fleet()
        try:
            if seal is None:
                heartbeat(heartbeat_fields(cache, datetime.now(timezone.utc)), audit_anchor_for_fleet())
            else:
                heartbeat(heartbeat_fields(cache, datetime.now(timezone.utc)), audit_anchor_for_fleet(), seal)
        except FleetError as exc:
            _log("rights.sync", heartbeat="not_delivered", error=str(exc))
        else:
            if seal is not None:
                # Fleet has it (2xx): it no longer stays on this machine.
                audit_seal.handed_over("fleet")
                _log("rights.sync", audit_seal="handed_over_to_fleet")
    return SYNC_EXIT[outcome]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["apply-default"]:
        return apply_default()
    if args == ["sync"]:
        return sync()
    print("usage: eira-rights-apply apply-default | sync", file=sys.stderr)
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
