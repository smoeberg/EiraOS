#!/usr/bin/env python3
"""Generate tests/vectors/rights-set/ for EIRA Rights Set 1.0.

The vectors are the shared contract between eira-os and eira-fleet-control
(EIRA-RIGHTS-SET §8). eira-os runs them against its verifier; Fleet runs
tests/vectors/rights-signing/ against its signer with
scripts/rights_vectors_conformance.py and pins the set's version in
tests/vectors/MANIFEST.json. Regenerating must be deliberate — the output is
committed, test_rights_set_contract.py fails if a vector's expectation and
the reference verifier disagree, and test_rights_vectors_manifest.py fails if
a vector changes without a new manifest version (--bump).

The keys below are TEST KEYS derived from fixed seeds. They are not, and
must never become, trust anchors on a real device.

    python3 scripts/gen_rights_vectors.py           regenerate (same version)
    python3 scripts/gen_rights_vectors.py --bump    regenerate as a new version
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402

from app.rights import keys  # noqa: E402
from app.rights.contract import DOMAIN, canonical, signing_input  # noqa: E402

# EIRA_VECTORS_OUT lets the tests regenerate into a scratch directory.
VECTORS = Path(os.environ.get("EIRA_VECTORS_OUT") or ROOT / "tests" / "vectors")
OUT = VECTORS / "rights-set"
KEYS_OUT = VECTORS / "rights-keys"
SIGNING_OUT = VECTORS / "rights-signing"
MANIFEST = VECTORS / "MANIFEST.json"
# The directories the versioned set covers (UDVIKLINGSPLAN F1.9).
VERSIONED = ("rights-set", "rights-keys", "rights-signing")
ROOT_SEEDS = {"test-root-kk": bytes([0x66] * 32), "test-root-kk-expired": bytes([0x77] * 32)}
ROOT_NOT_AFTER = {"test-root-kk": "2036-01-01T00:00:00Z", "test-root-kk-expired": "2026-11-01T00:00:00Z"}

KEYS = {
    "test-tenant-kk-1": ("managed", bytes([0x11] * 32)),
    "test-release-1": ("default", bytes([0x22] * 32)),
    "test-tenant-kk-old": ("managed", bytes([0x44] * 32)),
}
# Anchors pinned at enroll expire (FLEET-RIGHTS-API §5).
NOT_AFTER = {"test-tenant-kk-1": "2036-01-01T00:00:00Z", "test-tenant-kk-old": "2026-11-01T00:00:00Z"}
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
            {"subject": {"principal": "did:eira:entra.9f3"}, "scope": "obj:sag:42",
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
    case("anchor-expired", "Gyldig signatur, men ankeret udløb før verifikationen (not_after).",
         text(sign(managed(), "test-tenant-kk-old")), {"ok": False, "reason": "anchor_expired"})
    case("anchor-expired-backdated", "Lækket, udløbet nøgle med tilbagedateret issued_at: afvises stadig.",
         text(sign(managed(issued_at="2026-10-20T00:00:00Z", expires_at="2026-11-15T00:00:00Z"),
                   "test-tenant-kk-old")),
         {"ok": False, "reason": "anchor_expired"})
    return v


def authorize_vectors() -> dict:
    doc = managed()
    q = []

    def query(name, principal, groups, scope, action, now, expect):
        q.append({"name": name, "principal": principal, "groups": groups, "scope": scope,
                  "action": action, "now": now, "expect": expect})

    query("group-grant", "did:eira:entra.a1", ["laerere"], "obj:sag:7", "edp:commitment_proposed", NOW,
          {"allowed": True, "reason": "granted", "grant_index": 0})
    query("group-without-grant", "did:eira:entra.a2", ["elever"], "obj:sag:7", "edp:commitment_proposed",
          NOW, {"allowed": False, "reason": "no_grant"})
    query("deny-wins", "did:eira:entra.a3", ["laerere", "vikarer"], "device:local",
          "system:power.request_action", NOW, {"allowed": False, "reason": "denied"})
    query("wildcard-does-not-match-type-root", "did:eira:entra.a1", ["laerere"], "obj:sag:", "edp:utterance",
          NOW, {"allowed": False, "reason": "no_grant"})
    query("scope-type-mismatch", "did:eira:entra.a1", ["laerere"], "obj:budget:7", "edp:utterance", NOW,
          {"allowed": False, "reason": "no_grant"})
    query("principal-grant-raises-assurance", "did:eira:entra.9f3", [], "obj:sag:42",
          "edp:value_transfer_requested", NOW,
          {"allowed": True, "reason": "granted", "grant_index": 2, "required_assurance": "eid_high"})
    query("temporary-grant-expired", "did:eira:entra.9f3", [], "obj:sag:42", "edp:value_transfer_requested",
          "2026-11-07T15:00:00Z", {"allowed": False, "reason": "no_grant"})
    query("set-expired", "did:eira:entra.a1", ["laerere"], "obj:sag:7", "edp:utterance",
          "2026-11-21T11:00:00Z", {"allowed": False, "reason": "expired"})
    return {"rights_set": doc, "queries": q}


def _root_sign(doc: dict, root_id: str, domain_input, *, seed: bytes | None = None) -> dict:
    doc = copy.deepcopy(doc)
    doc["signature"] = {"alg": "ed25519", "key_id": root_id, "value": "A" * 86}
    key = Ed25519PrivateKey.from_private_bytes(seed or ROOT_SEEDS[root_id])
    doc["signature"]["value"] = b64url(key.sign(domain_input(doc)))
    return doc


def key_vectors() -> list[dict]:
    ops = public(KEYS["test-tenant-kk-1"][1])

    def cert(**over):
        doc = {"eira_rights_key": "1", "key_id": "test-tenant-kk-1", "public_key": ops, "tenant_id": "kk",
               "not_before": "2026-11-01T00:00:00Z", "not_after": "2027-01-15T00:00:00Z"}
        doc.update(over)
        return doc

    def rev(seq, revoked, **over):
        doc = {"eira_rights_revocations": "1", "tenant_id": "kk", "sequence": seq,
               "issued_at": "2026-11-07T10:00:00Z", "revoked": revoked}
        doc.update(over)
        return doc

    c, r = keys.signing_input_certificate, keys.signing_input_revocations
    v = []

    def case(name, description, kind, doc, expect, previous=None):
        v.append({"name": name, "description": description, "kind": kind, "raw": text(doc),
                  "tenant_id": "kk", "now": NOW, "previous": previous, "expect": expect})

    ok = {"ok": True}
    case("cert-valid", "Driftsnøgle certificeret af roden.", "certificate", _root_sign(cert(), "test-root-kk", c), ok)
    case("cert-wrong-tenant", "Certifikat til en anden tenant.", "certificate",
         _root_sign(cert(tenant_id="other"), "test-root-kk", c), {"ok": False, "reason": "wrong_tenant"})
    case("cert-lifetime-over-cap", "91 dage (loft: 90).", "certificate",
         _root_sign(cert(not_after="2027-01-31T00:00:00Z"), "test-root-kk", c),
         {"ok": False, "reason": "lifetime_over_cap"})
    case("cert-expired", "Certifikatet er udløbet.", "certificate",
         _root_sign(cert(not_before="2026-08-10T00:00:00Z", not_after="2026-11-01T00:00:00Z"), "test-root-kk", c),
         {"ok": False, "reason": "expired"})
    case("cert-root-expired", "Roden udløb før verifikationen.", "certificate",
         _root_sign(cert(), "test-root-kk-expired", c), {"ok": False, "reason": "root_expired"})
    case("cert-unknown-root", "Signeret af en nøgle, der ikke er en fastgjort rod.", "certificate",
         _root_sign(cert(), "test-root-unknown", c, seed=bytes([0x88] * 32)), {"ok": False, "reason": "unknown_root"})
    case("cert-signed-by-ops-key", "Driftsnøglen udgiver sig for roden.", "certificate",
         _root_sign(cert(), "test-root-kk", c, seed=KEYS["test-tenant-kk-1"][1]), {"ok": False, "reason": "bad_signature"})
    case("cert-wrong-domain", "Rodens signatur over sæt-domænet EIRAOS-RIGHTS-V1.", "certificate",
         _root_sign(cert(), "test-root-kk", signing_input), {"ok": False, "reason": "bad_signature"})
    case("cert-root-as-key", "En rod kan ikke være driftsnøgle.", "certificate",
         _root_sign(cert(key_id="test-root-kk"), "test-root-kk", c), {"ok": False, "reason": "malformed"})
    first = _root_sign(rev(1, ["old-1"]), "test-root-kk", r)
    prev = {"sequence": 1, "revoked": ["old-1"], "digest": "sha256:" + __import__("hashlib").sha256(r(first)).hexdigest()}
    case("rev-valid", "Første tilbagekaldelsesliste.", "revocations", first, ok)
    case("rev-grows", "Højere sekvens, flere nøgler.", "revocations",
         _root_sign(rev(2, ["old-1", "old-2"]), "test-root-kk", r), ok, previous=prev)
    case("rev-rollback", "Lavere sekvens.", "revocations",
         _root_sign(rev(1, ["old-1"], issued_at="2026-11-06T00:00:00Z"), "test-root-kk", r),
         {"ok": False, "reason": "sequence_rollback"}, previous={**prev, "sequence": 2})
    case("rev-unrevoke", "Højere sekvens, men old-1 er fjernet.", "revocations",
         _root_sign(rev(2, []), "test-root-kk", r), {"ok": False, "reason": "sequence_rollback"}, previous=prev)
    case("rev-conflict", "Samme sekvens, andet indhold.", "revocations",
         _root_sign(rev(1, ["old-1", "sneaked-in"]), "test-root-kk", r),
         {"ok": False, "reason": "sequence_conflict"}, previous=prev)
    case("rev-signed-by-ops-key", "Driftsnøglen kan ikke tilbagekalde.", "revocations",
         _root_sign(rev(1, ["old-1"]), "test-root-kk", r, seed=KEYS["test-tenant-kk-1"][1]),
         {"ok": False, "reason": "bad_signature"})
    return v


def signing_vectors() -> list[dict]:
    """What Fleet must produce byte for byte: the unsigned document and the
    test key in, the canonical signed document out (Ed25519 is deterministic).
    One case per document Fleet signs and per signing domain."""
    v = []

    def case(name, description, kind, signed, seed):
        unsigned = copy.deepcopy(signed)
        del unsigned["signature"]["value"]
        v.append({"name": name, "description": description, "kind": kind,
                  "seed_hex": seed.hex(), "document": unsigned, "expect_raw": text(signed)})

    case("rights-set-managed", "Managed-sæt signeret med tenantens driftsnøgle (EIRAOS-RIGHTS-V1).",
         "rights_set", sign(managed(), "test-tenant-kk-1"), KEYS["test-tenant-kk-1"][1])
    case("rights-set-default", "Bundlens default-sæt signeret med release-nøglen (EIRAOS-RIGHTS-V1).",
         "rights_set", sign(default_set(), "test-release-1"), KEYS["test-release-1"][1])
    case("rights-set-unicode", "Ikke-ASCII i strenge: JCS skriver dem som UTF-8, ikke som \\u-escapes.",
         "rights_set",
         sign(managed(issued_by={"api_call_id": "req-lærer-7f3a", "fleet": "fleet.kk.example"}),
              "test-tenant-kk-1"),
         KEYS["test-tenant-kk-1"][1])
    ops = public(KEYS["test-tenant-kk-1"][1])
    cert = {"eira_rights_key": "1", "key_id": "test-tenant-kk-1", "public_key": ops, "tenant_id": "kk",
            "not_before": "2026-11-01T00:00:00Z", "not_after": "2027-01-15T00:00:00Z"}
    case("key-certificate", "Driftsnøglens certifikat signeret med tenantens rod (EIRAOS-RIGHTS-KEY-V1).",
         "key_certificate", _root_sign(cert, "test-root-kk", keys.signing_input_certificate),
         ROOT_SEEDS["test-root-kk"])
    rev = {"eira_rights_revocations": "1", "tenant_id": "kk", "sequence": 2,
           "issued_at": "2026-11-07T10:00:00Z", "revoked": ["old-1", "old-2"]}
    case("revocations", "Tilbagekaldelseslisten signeret med tenantens rod (EIRAOS-RIGHTS-REVOKE-V1).",
         "revocations", _root_sign(rev, "test-root-kk", keys.signing_input_revocations),
         ROOT_SEEDS["test-root-kk"])
    return v


def _file_hashes() -> dict[str, str]:
    return {
        path.relative_to(VECTORS).as_posix(): "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        for directory in VERSIONED
        for path in sorted((VECTORS / directory).glob("*.json"))
    }


def set_hash(files: dict[str, str]) -> str:
    """One hash over the whole set: names and contents."""
    body = "".join(f"{name}\0{digest}\n" for name, digest in sorted(files.items()))
    return "sha256:" + hashlib.sha256(body.encode()).hexdigest()


def write_manifest(bump: bool) -> dict:
    """Record the set's hash under its version. A changed set needs --bump,
    so a pinned version always means the same files on both sides."""
    previous = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"version": 0, "history": {}}
    files = _file_hashes()
    digest = set_hash(files)
    version = previous["version"]
    history = dict(previous["history"])
    if bump or version == 0:
        version += 1
        history[str(version)] = digest
    elif history.get(str(version)) != digest:
        raise SystemExit(
            f"the vectors changed but version {version} is recorded with another hash: "
            "run with --bump to publish a new version"
        )
    manifest = {
        "name": "eira-rights-vectors",
        "note": "Shared by eira-os (verifier) and eira-fleet-control (signer). TEST KEYS ONLY.",
        "version": version,
        "set_hash": digest,
        "covers": list(VERSIONED),
        "files": files,
        "history": history,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def main() -> None:
    bump = "--bump" in sys.argv[1:]
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    context = {
        "note": "TEST KEYS ONLY. Never trust anchors on a real device.",
        "domain": DOMAIN.decode(),
        "max_ttl_seconds": {"managed": 30 * 24 * 3600, "default": 400 * 24 * 3600},
        "anchors": {
            kid: {"kind": kind, "public_key": public(seed), **({"not_after": NOT_AFTER[kid]} if kid in NOT_AFTER else {})}
            for kid, (kind, seed) in KEYS.items()
        },
        "registry": REGISTRY,
    }
    (OUT / "_context.json").write_text(json.dumps(context, indent=2, ensure_ascii=False) + "\n")
    for vector in apply_vectors():
        (OUT / f"apply-{vector['name']}.json").write_text(
            json.dumps(vector, indent=2, ensure_ascii=False) + "\n"
        )
    (OUT / "authorize.json").write_text(json.dumps(authorize_vectors(), indent=2, ensure_ascii=False) + "\n")
    KEYS_OUT.mkdir(parents=True, exist_ok=True)
    for old in KEYS_OUT.glob("*.json"):
        old.unlink()
    (KEYS_OUT / "_context.json").write_text(json.dumps({
        "note": "TEST KEYS ONLY. Never roots on a real device.",
        "max_key_lifetime_seconds": int(keys.MAX_KEY_LIFETIME.total_seconds()),
        "roots": {rid: {"public_key": public(seed), "not_after": ROOT_NOT_AFTER[rid]} for rid, seed in ROOT_SEEDS.items()},
    }, indent=2) + "\n")
    for vector in key_vectors():
        (KEYS_OUT / f"{vector['name']}.json").write_text(json.dumps(vector, indent=2, ensure_ascii=False) + "\n")
    SIGNING_OUT.mkdir(parents=True, exist_ok=True)
    for old in SIGNING_OUT.glob("*.json"):
        old.unlink()
    for vector in signing_vectors():
        (SIGNING_OUT / f"sign-{vector['name']}.json").write_text(
            json.dumps(vector, indent=2, ensure_ascii=False) + "\n"
        )
    write_manifest(bump)


if __name__ == "__main__":
    main()
