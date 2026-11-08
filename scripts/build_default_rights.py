#!/usr/bin/env python3
"""Build the bundle's signed default rights set (EIRA-RIGHTS-SET-1.0 §5).

    scripts/build_default_rights.py OUTPUT_DIR

Writes OUTPUT_DIR/default.json and OUTPUT_DIR/anchors.json.

The signing key is generated for this build, used once and never written
anywhere: the set and its anchor ship in the same package, so the package's
own signature (apt) is the trust root. A long-lived key would protect nothing
more and would be one more secret that can leak. Consequence: a default set
can only be replaced by a new package, which is exactly how it is renewed.

`version` and `issued_at` are the real build time in seconds, so every later
package supersedes the earlier one (§4 rule 6). SOURCE_DATE_EPOCH is ignored
on purpose: dpkg-buildpackage sets it from debian/changelog, which would give
every build of the same changelog the same version with different content
(`version_conflict` on upgrade) and an expiry counted from the changelog date.
The set is not reproducible anyway: its key is fresh each build.
EIRA_RIGHTS_BUILD_EPOCH overrides the time for tests only.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402

from app.gate.policy import REGISTRY  # noqa: E402
from app.rights import contract  # noqa: E402

# The private machine (ADR-0003 (b)): its one signed-in user may do what the
# gate offers on their own objects and this device. The gate's consent,
# rendering and audit still apply to every action.
LIFETIME = timedelta(days=365)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _ts(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def build(out: Path) -> dict:
    epoch = int(os.environ.get("EIRA_RIGHTS_BUILD_EPOCH") or datetime.now(timezone.utc).timestamp())
    issued = datetime.fromtimestamp(epoch, timezone.utc)
    keys = sorted(contract.action_keys(REGISTRY))
    edp_keys = [k for k in keys if k.startswith("edp:")]
    system_keys = [k for k in keys if k.startswith("system:")]

    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    key_id = f"build-{epoch}-{public.hex()[:12]}"

    doc = {
        "eira_rights": "1",
        "rights_set_id": str(uuid.uuid4()),
        "kind": "default",
        "tenant_id": "unmanaged",
        "device_id": "*",
        "version": epoch,
        "issued_at": _ts(issued),
        "expires_at": _ts(issued + LIFETIME),
        "template": {"id": "personal", "version": "1"},
        "issued_by": {"api_call_id": f"package-build-{epoch}", "fleet": "eira-os-package"},
        "grants": [
            {"subject": {"authenticated": True}, "scope": "obj:sag:*", "actions": edp_keys},
            {"subject": {"authenticated": True}, "scope": "device:local", "actions": system_keys},
        ],
        "denies": [],
        "signature": {"alg": "ed25519", "key_id": key_id, "value": "A" * 86},
    }
    doc["signature"]["value"] = _b64url(key.sign(contract.signing_input(doc)))
    del key  # never persisted

    raw = contract.canonical(doc)
    anchors = {"anchors": {key_id: {"kind": "default", "public_key": _b64url(public)}}}
    verdict = contract.verify(
        raw,
        anchors={key_id: contract.Anchor("default", public)},
        device=contract.Device(enrolled=False),
        active=None,
        now=issued,
        registry=REGISTRY,
    )
    if not verdict.ok:
        raise SystemExit(f"built default set does not verify: {verdict.reason}")

    out.mkdir(parents=True, exist_ok=True)
    (out / "default.json").write_bytes(raw)
    (out / "anchors.json").write_text(json.dumps(anchors, indent=2, sort_keys=True) + "\n")
    return doc


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_default_rights.py OUTPUT_DIR")
    doc = build(Path(sys.argv[1]))
    print(f"default rights set v{doc['version']} expires {doc['expires_at']}")


if __name__ == "__main__":
    main()
