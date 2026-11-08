"""Rights-set apply for the endpoint (EIRA-RIGHTS-SET-1.0 §4, §5).

This is the apply half of `eira-governance-agent`. Today it applies the
bundle's signed default set on an unmanaged device; fetching managed sets
from Fleet plugs into `apply()` unchanged.

    eira-rights-apply apply-default

Exit codes: 0 applied, no-op or not applicable (enrolled device);
1 rejected (the active set is kept; the reason is logged); 2 bundle missing.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from app.rights import contract
from app.rights.cache import RightsCache

BUNDLE_DIR = Path(os.environ.get("EIRA_RIGHTS_BUNDLE_DIR", "/usr/lib/eira-os/rights"))
# Written by enrollment (not yet built). Its absence means unmanaged.
ENROLLMENT = Path(os.environ.get("EIRA_ENROLLMENT_FILE", "/etc/eira/enrollment.json"))


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


def device_identity(path: Path | None = None) -> contract.Device:
    path = path if path is not None else ENROLLMENT
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return contract.Device(enrolled=False)
    return contract.Device(enrolled=True, tenant_id=data["tenant_id"], device_id=data["device_id"])


def apply(
    raw: bytes,
    *,
    anchors: Mapping[str, contract.Anchor],
    device: contract.Device,
    cache: RightsCache,
    registry: Iterable[str],
    wall_now: datetime,
) -> contract.Verdict:
    """Verify against the active set and install atomically, or change nothing."""
    # §4.1: never judge a set on a wall clock that went back past what this
    # device has already seen.
    high_water = cache.high_water()
    now = max(wall_now, high_water) if high_water else wall_now
    verdict = contract.verify(
        raw, anchors=anchors, device=device, active=cache.active_meta(), now=now, registry=registry
    )
    if verdict.ok:
        cache.install(raw, verdict, wall_now)
    return verdict


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
    device = device_identity()
    if device.enrolled:
        _log("rights.apply", result="not_applicable", reason="device is enrolled; Fleet supplies the set")
        return 0
    verdict = apply(
        raw,
        anchors=anchors,
        device=device,
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


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["apply-default"]:
        print("usage: eira-rights-apply apply-default", file=sys.stderr)
        return 64
    return apply_default()


if __name__ == "__main__":
    raise SystemExit(main())
