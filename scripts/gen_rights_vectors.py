#!/usr/bin/env python3
"""Generate tests/vectors/rights-set/ for EIRA Rights Set 1.0.

The vectors are the shared contract between eira-os and eira-fleet-control:
both repos run the same files in CI. Regenerating must be deliberate — the
output is committed, and test_rights_set_contract.py fails if a vector's
expectation and the reference verifier disagree.

The keys below are TEST KEYS derived from fixed seeds. They are not, and
must never become, trust anchors on a real device.

    python3 scripts/gen_rights_vectors.py
"""

from __future__ import annotations

import base64
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402

from app.rights.contract import DOMAIN, canonical, signing_input  # noqa: E402

OUT = ROOT / "tests" / "vectors" / "rights-set"

KEYS = {
    "test-tenant-kk-1": ("managed", bytes([0x11] * 32)),
    "test-release-1": ("default", bytes([0x22] * 32)),
}
REGISTRY = [
    "edp:utterance",
    "edp:commitment_proposed",
    "edp:commitment_accepted",
    "edp:value_transfer_requested",
    "system:power.request_action",
]
NOW = "2026-11-07T12:00:00Z"
MANAGED_DEVICE = {"enrolled": True, "tenant_id": "kk", "device_id": "dev-0001"}
UNMANAGED_DEVICE = {"enrolled": False}


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def public(seed: bytes) -> str:
    raw = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    return b64url(raw)


def sign(doc: dict, key_id: str, *, domain: bytes = DOMAIN) -> dict:
    doc = copy.deepcopy(doc)
    doc["signature"] = {"alg": "ed25519", "key_id": key_id, "value": "A" * 86}
    message = signing_input(doc)
    if domain != DOMAIN:
        message = bytes([len(domain)]) + domain + message[1 + len(DOMAIN):]
    seed = KEYS[key_id][1]
    doc["signature"]["value"] = b64url(Ed25519PrivateKey.from_private_bytes(seed).sign(message))
    return doc


def managed(**over) -> dict:
    doc = {
        "eira_rights": "1",
        "rights_set_id": "0190f5a0-0000-7000-8000-00000000abcd",
        "kind": "managed",
        "tenant_id": "kk",
        "device_id": "dev-0001",
        "version": 42,
        "issued_at": "2026-11-07T11:00:00Z",
        "expires_at": "2026-11-21T11:00:00Z",
        "template": {"id": "skoleforvaltning-laerer", "version": "3"},
        "issued_by": {"api_call_id": "req-7f3a", "fleet": "fleet.kk.example"},
        "grants": [
            {"subject": {"group": "laerere"}, "scope": "obj:sag:*",
             "actions": ["edp:utterance", "edp:commitment_proposed", "edp:commitment_accepted"]},
            {"subject": {"group": "laerere"}, "scope": "device:local",
             "actions": ["system:power.request_action"]},
            {"subject": {"principal": "entra:oid:9f3"}, "scope": "obj:sag:42",
             "actions": ["edp:value_transfer_requested"],
             "expires_at": "2026-11-07T15:00:00Z", "required_assurance": "eid_high"},
        ],
        "denies": [
            {"subject": {"group": "vikarer"}, "scope": "device:local",
             "actions": ["system:power.request_action"]},
        ],
    }
    doc.update(over)
    return doc


def default_set(**over) -> dict:
    doc = managed(kind="default", tenant_id="unmanaged", device_id="*", version=1,
                  template={"id": "personal", "version": "1"},
                  issued_by={"api_call_id": "release-1.0.0", "fleet": "release.eira.example"},
                  grants=[{"subject": {"authenticated": True}, "scope": "device:local",
                           "actions": ["system:power.request_action"]}],
                  denies=[])
    doc.update(over)
    return doc


def text(doc: dict) -> str:
    return canonical(doc).decode()


def active_of(doc: dict) -> dict:
    from app.rights.contract import content_hash

    return {"version": doc["version"], "content_hash": content_hash(doc), "tenant_id": doc["tenant_id"]}


def apply_vectors() -> list[dict]:
    good = sign(managed(), "test-tenant-kk-1")
    v = []

    def case(name, description, raw, expect, device=MANAGED_DEVICE, active=None, now=NOW):
        v.append({"name": name, "description": description, "raw": raw,
                  "device": device, "active": active, "now": now, "expect": expect})

    ok = {"ok": True}
    case("valid-managed", "Gyldigt managed-sæt på den rigtige enhed.", text(good), ok)
    case("valid-default-unmanaged", "Bundlens default-sæt på en ikke-enrolled enhed.",
         text(sign(default_set(), "test-release-1")), ok, device=UNMANAGED_DEVICE)
    case("expired", "now ≥ expires_at.", text(good), {"ok": False, "reason": "expired"},
         now="2026-11-21T11:00:00Z")
    case("not-yet-valid", "issued_at mere end 5 min. i fremtiden.", text(good),
         {"ok": False, "reason": "not_yet_valid"}, now="2026-11-07T10:54:00Z")
    case("version-rollback", "Lavere version end det aktive sæt.",
         text(good), {"ok": False, "reason": "version_rollback"},
         active={"version": 43, "content_hash": "sha256:" + "0" * 64, "tenant_id": "kk"})
    case("same-version-same-content", "Samme version og indhold: idempotent no-op.",
         text(good), {"ok": True, "noop": True}, active=active_of(good))
    case("same-version-other-content", "Samme version, andet indhold.",
         text(good), {"ok": False, "reason": "version_conflict"},
         active={"version": 42, "content_hash": "sha256:" + "0" * 64, "tenant_id": "kk"})
    case("wrong-device", "device_id matcher ikke enroll-identiteten.",
         text(sign(managed(device_id="dev-9999"), "test-tenant-kk-1")),
         {"ok": False, "reason": "wrong_device"})
    case("wrong-tenant", "tenant_id matcher ikke enroll-identiteten.",
         text(sign(managed(tenant_id="other"), "test-tenant-kk-1")),
         {"ok": False, "reason": "wrong_tenant"})
    case("wrong-domain-prefix", "Gyldig Ed25519-signatur, men over domænet EIRAOS-EVENT-V1.",
         text(sign(managed(), "test-tenant-kk-1", domain=b"EIRAOS-EVENT-V1")),
         {"ok": False, "reason": "bad_signature"})
    tampered = copy.deepcopy(good)
    tampered["grants"][0]["actions"].append("edp:value_transfer_requested")
    case("tampered-after-signing", "Indhold ændret efter signering.", text(tampered),
         {"ok": False, "reason": "bad_signature"})
    case("unknown-key-id", "key_id findes ikke blandt ankrene.",
         text({**good, "signature": {**good["signature"], "key_id": "test-unknown"}}),
         {"ok": False, "reason": "unknown_key_id"})
    case("managed-signed-by-release-key", "Managed-sæt signeret med release-nøglen.",
         text(sign(managed(), "test-release-1")), {"ok": False, "reason": "wrong_anchor"})
    no_template = sign(managed(), "test-tenant-kk-1")
    del no_template["template"]
    case("missing-template", "Sæt uden template.", text(no_template), {"ok": False, "reason": "schema"})
    case("ttl-over-cap", "expires_at - issued_at er 31 dage (loft: 30).",
         text(sign(managed(expires_at="2026-12-08T11:00:00Z"), "test-tenant-kk-1")),
         {"ok": False, "reason": "ttl_over_cap"})
    case("unknown-action", "Handlingsnøgle, som den installerede gate ikke kender.",
         text(sign(managed(grants=[{"subject": {"group": "laerere"}, "scope": "device:local",
                                    "actions": ["system:disk.format"]}]), "test-tenant-kk-1")),
         {"ok": False, "reason": "unknown_action"})
    case("wildcard-action", "* i actions.",
         text(sign(managed(grants=[{"subject": {"group": "laerere"}, "scope": "device:local",
                                    "actions": ["*"]}]), "test-tenant-kk-1")),
         {"ok": False, "reason": "schema"})
    case("unknown-field", "Ukendt topfelt.",
         text(sign(managed(extra="x"), "test-tenant-kk-1")), {"ok": False, "reason": "schema"})
    float_raw = text(good).replace('"version":42', '"version":42.0')
    case("float-version", "version som float (42.0). JSON Schema ville godtage den som heltal.",
         float_raw, {"ok": False, "reason": "malformed"})
    dup = text(good).replace('"eira_rights":"1"', '"eira_rights":"1","eira_rights":"1"', 1)
    case("duplicate-key", "Dobbelt nøgle i JSON (to parsere kunne se forskellige sæt).", dup,
         {"ok": False, "reason": "malformed"})
    case("grant-outlives-set", "En grants expires_at ligger efter sættets.",
         text(sign(managed(grants=[{"subject": {"group": "laerere"}, "scope": "device:local",
                                    "actions": ["system:power.request_action"],
                                    "expires_at": "2026-12-01T00:00:00Z"}]), "test-tenant-kk-1")),
         {"ok": False, "reason": "grant_outlives_set"})
    case("default-on-enrolled", "Default-sæt på en enrolled enhed.",
         text(sign(default_set(), "test-release-1")), {"ok": False, "reason": "default_on_enrolled"})
    case("managed-on-unmanaged", "Managed-sæt på en enhed, der ikke er enrolled.", text(good),
         {"ok": False, "reason": "wrong_tenant"}, device=UNMANAGED_DEVICE)
    case("default-ttl-365-days", "Default-sæt med 365 dages levetid (loft: 400).",
         text(sign(default_set(expires_at="2027-11-07T11:00:00Z"), "test-release-1")), ok,
         device=UNMANAGED_DEVICE)
    case("default-ttl-over-cap", "Default-sæt med 401 dages levetid (loft: 400).",
         text(sign(default_set(expires_at="2027-12-13T11:00:00Z"), "test-release-1")),
         {"ok": False, "reason": "ttl_over_cap"}, device=UNMANAGED_DEVICE)
    case("managed-ttl-400-days", "Managed-sæt kan ikke låne default-loftet.",
         text(sign(managed(expires_at="2027-12-12T11:00:00Z"), "test-tenant-kk-1")),
         {"ok": False, "reason": "ttl_over_cap"})
    return v


def authorize_vectors() -> dict:
    doc = managed()
    q = []

    def query(name, principal, groups, scope, action, now, expect):
        q.append({"name": name, "principal": principal, "groups": groups, "scope": scope,
                  "action": action, "now": now, "expect": expect})

    query("group-grant", "entra:oid:a1", ["laerere"], "obj:sag:7", "edp:commitment_proposed", NOW,
          {"allowed": True, "reason": "granted", "grant_index": 0})
    query("group-without-grant", "entra:oid:a2", ["elever"], "obj:sag:7", "edp:commitment_proposed",
          NOW, {"allowed": False, "reason": "no_grant"})
    query("deny-wins", "entra:oid:a3", ["laerere", "vikarer"], "device:local",
          "system:power.request_action", NOW, {"allowed": False, "reason": "denied"})
    query("wildcard-does-not-match-type-root", "entra:oid:a1", ["laerere"], "obj:sag:", "edp:utterance",
          NOW, {"allowed": False, "reason": "no_grant"})
    query("scope-type-mismatch", "entra:oid:a1", ["laerere"], "obj:budget:7", "edp:utterance", NOW,
          {"allowed": False, "reason": "no_grant"})
    query("principal-grant-raises-assurance", "entra:oid:9f3", [], "obj:sag:42",
          "edp:value_transfer_requested", NOW,
          {"allowed": True, "reason": "granted", "grant_index": 2, "required_assurance": "eid_high"})
    query("temporary-grant-expired", "entra:oid:9f3", [], "obj:sag:42", "edp:value_transfer_requested",
          "2026-11-07T15:00:00Z", {"allowed": False, "reason": "no_grant"})
    query("set-expired", "entra:oid:a1", ["laerere"], "obj:sag:7", "edp:utterance",
          "2026-11-21T11:00:00Z", {"allowed": False, "reason": "expired"})
    return {"rights_set": doc, "queries": q}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    context = {
        "note": "TEST KEYS ONLY. Never trust anchors on a real device.",
        "domain": DOMAIN.decode(),
        "max_ttl_seconds": {"managed": 30 * 24 * 3600, "default": 400 * 24 * 3600},
        "anchors": {kid: {"kind": kind, "public_key": public(seed)} for kid, (kind, seed) in KEYS.items()},
        "registry": REGISTRY,
    }
    (OUT / "_context.json").write_text(json.dumps(context, indent=2, ensure_ascii=False) + "\n")
    for vector in apply_vectors():
        (OUT / f"apply-{vector['name']}.json").write_text(
            json.dumps(vector, indent=2, ensure_ascii=False) + "\n"
        )
    (OUT / "authorize.json").write_text(json.dumps(authorize_vectors(), indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
