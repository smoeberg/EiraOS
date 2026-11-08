"""Tenant root and operational keys (EIRA-RIGHTS-SET-1.3 §3.1)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.gate.policy import REGISTRY
from app.rights import agent, contract, fleet_api, keys
from app.rights.cache import RightsCache
from tests.rights_helpers import DEVICE, KEY_ID, ROOT_ID, TestFleet
from tests.test_gate_kernel import Clock


@pytest.fixture
def tenant(tmp_path):
    clock = Clock()
    signer = TestFleet(tmp_path / "rights", clock)
    roots = fleet_api.read_enrollment(signer.enrollment_path).rights_roots
    return signer, roots, clock


def verify(signer, roots, raw, clock, **kw):
    return keys.verify_certificate(raw, roots=roots, tenant_id=DEVICE.tenant_id, now=clock(), **kw)


def test_valid_certificate(tenant):
    signer, roots, clock = tenant
    cert = verify(signer, roots, signer.certificate(), clock)
    assert (cert.key_id, cert.issuer, cert.public_key) == (KEY_ID, ROOT_ID, signer.public)


def test_certificate_rules(tenant):
    signer, roots, clock = tenant
    now = clock()
    cases = {
        "wrong_tenant": signer.certificate(tenant_id="other"),
        "lifetime_over_cap": signer.certificate(not_before=now, not_after=now + timedelta(days=91)),
        "not_yet_valid": signer.certificate(not_before=now + timedelta(days=1), not_after=now + timedelta(days=30)),
        "expired": signer.certificate(not_before=now - timedelta(days=60), not_after=now - timedelta(days=1)),
    }
    for reason, raw in cases.items():
        with pytest.raises(keys.KeyRejected) as exc:
            verify(signer, roots, raw, clock)
        assert exc.value.reason == reason


def test_operational_key_cannot_certify_another_key(tenant):
    signer, roots, clock = tenant
    raw = signer.certificate(key_id="ops-2", root=signer._key)  # signed by the ops key, not the root
    with pytest.raises(keys.KeyRejected) as exc:
        verify(signer, roots, raw, clock)
    assert exc.value.reason == "bad_signature"


def test_expired_root_certifies_nothing(tenant):
    signer, roots, clock = tenant
    with pytest.raises(keys.KeyRejected) as exc:
        keys.verify_certificate(
            signer.certificate(), roots=roots, tenant_id=DEVICE.tenant_id, now=clock() + timedelta(days=4000)
        )
    assert exc.value.reason == "root_expired"


def test_root_never_signs_a_rights_set(tenant):
    """A set signed with a root key is not verifiable: roots are not anchors."""
    signer, roots, clock = tenant
    signer.version = 1
    doc = signer.document()
    doc["signature"] = {"alg": "ed25519", "key_id": ROOT_ID, "value": "A" * 86}
    doc["signature"]["value"] = fleet_api.encode_rights_set(signer._root.sign(contract.signing_input(doc)))
    anchors = keys.operational_anchors(
        [signer.certificate()], roots=roots, tenant_id=DEVICE.tenant_id, revocations=None, now=clock()
    )
    verdict = contract.verify(contract.canonical(doc), anchors=anchors, device=DEVICE, active=None,
                              now=clock(), registry=REGISTRY)
    assert verdict.reason == "unknown_key_id"


def test_a_root_id_cannot_be_an_operational_key(tenant):
    signer, roots, clock = tenant
    with pytest.raises(keys.KeyRejected) as exc:
        verify(signer, roots, signer.certificate(key_id=ROOT_ID), clock)
    assert exc.value.reason == "malformed"


def test_extra_field_in_certificate_is_malformed(tenant):
    signer, roots, clock = tenant
    doc = json.loads(signer.certificate())
    doc["kind"] = "root"
    with pytest.raises(keys.KeyRejected) as exc:
        verify(signer, roots, contract.canonical(doc), clock)
    assert exc.value.reason in {"malformed", "bad_signature"}


# --- revocation list ------------------------------------------------------------


def rev(signer, roots, clock, previous=None):
    return keys.verify_revocations(
        signer.revocations(), roots=roots, tenant_id=DEVICE.tenant_id, now=clock(), previous=previous
    )


def test_revocation_sequence_only_goes_up_and_list_only_grows(tenant):
    signer, roots, clock = tenant
    signer.revoke("old-1")
    first = rev(signer, roots, clock)
    signer.revoke("old-2")
    second = rev(signer, roots, clock, previous=first)
    assert second.revoked == {"old-1", "old-2"}
    signer.revocation_sequence = 1  # replay an older list
    signer.revoked = ["old-1"]
    with pytest.raises(keys.KeyRejected) as exc:
        rev(signer, roots, clock, previous=second)
    assert exc.value.reason == "sequence_rollback"
    signer.revocation_sequence = 3  # newer, but un-revokes old-2
    with pytest.raises(keys.KeyRejected) as exc:
        rev(signer, roots, clock, previous=second)
    assert exc.value.reason == "sequence_rollback"


def test_same_sequence_other_content_conflicts(tenant):
    signer, roots, clock = tenant
    signer.revoke("old-1")
    first = rev(signer, roots, clock)
    signer.revoked = ["old-1", "sneaked-in"]
    with pytest.raises(keys.KeyRejected) as exc:
        rev(signer, roots, clock, previous=first)
    assert exc.value.reason == "sequence_conflict"


# --- end to end through the agent and the gate's view ---------------------------


class Fleet:
    def __init__(self, signer):
        self.signer = signer
        self.reports = []

    def desired_rights(self, active_version):
        certs, revocations = self.signer.key_material()
        body = {"rights_keys": [fleet_api.encode_rights_set(c) for c in certs]}
        if revocations:
            body["rights_revocations"] = fleet_api.encode_rights_set(revocations)
        if active_version != self.signer.version:
            body["rights_set"] = fleet_api.encode_rights_set(contract.canonical(self.signer.document()))
        return fleet_api.parse_desired_state(body)

    def report_apply(self, report):
        self.reports.append(report)


@pytest.fixture
def device(tmp_path):
    clock = Clock()
    signer = TestFleet(tmp_path / "unused", clock)
    signer.version = 1
    signer.grant("obj:sag:*", principal="did:eira:anne")
    enrolled = fleet_api.read_enrollment(signer.enrollment_path)
    cache = RightsCache(tmp_path / "rights", enrollment_path=signer.enrollment_path)
    fleet = Fleet(signer)

    def sync():
        return agent.sync_once(fleet, enrolled, cache, registry=REGISTRY, wall_now=clock())

    return signer, cache, fleet, sync, clock


def test_revoking_the_signing_key_removes_the_cached_sets_rights(device):
    signer, cache, fleet, sync, clock = device
    assert sync() == "applied"
    assert cache.resolve(clock()).state == "active"
    signer.revoke(KEY_ID)
    assert sync() == "unchanged"  # nothing newer, but the revocation arrived
    state = cache.resolve(clock())
    assert (state.state, state.reason, state.rights) == ("missing", "signing_key_revoked", None)


def test_set_from_a_revoked_key_is_rejected_as_key_revoked(device):
    signer, cache, fleet, sync, _ = device
    signer.revoke(KEY_ID)
    assert sync() == "rejected"
    assert fleet.reports[-1].reason == "key_revoked"


def test_rotation_without_re_enrolling(device):
    """The root certifies a new operational key and revokes the old one; the
    device follows without touching its enrollment."""
    signer, cache, fleet, sync, clock = device
    assert sync() == "applied"
    new_key = Ed25519PrivateKey.generate()
    new_public = new_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    old_cert = signer.certificate()
    new_cert = signer.certificate(key_id="test-fleet-2", public=new_public)
    signer.key_material = lambda: ([old_cert, new_cert], signer.revocations() if signer.revocation_sequence else None)
    signer.revoke(KEY_ID)
    signer._key, signer.public = new_key, new_public
    original_document = signer.document

    def document():
        doc = original_document()
        doc["signature"] = {"alg": "ed25519", "key_id": "test-fleet-2", "value": "A" * 86}
        doc["signature"]["value"] = fleet_api.encode_rights_set(new_key.sign(contract.signing_input(doc)))
        return doc

    signer.document = document
    signer.version = 2
    assert sync() == "applied"
    state = cache.resolve(clock())
    assert (state.state, state.rights.version) == ("active", 2)


def test_older_revocation_list_from_fleet_is_ignored(device):
    signer, cache, fleet, sync, clock = device
    signer.revoke("old-1").revoke("old-2")
    sync()
    _, stored = cache.key_material()
    signer.revocation_sequence, signer.revoked = 1, ["old-1"]
    sync()
    assert cache.key_material()[1] == stored


def test_expired_operational_key_reports_anchor_expired(device):
    signer, cache, fleet, sync, clock = device
    signer.cert_not_after = clock() + timedelta(hours=1)
    clock.now += timedelta(hours=2)
    signer.version = 1
    assert sync() == "rejected"
    assert fleet.reports[-1].reason == "anchor_expired"


# --- shared vectors (eira-fleet-control runs the same files) ---------------------

KEY_VECTORS = sorted((Path(__file__).parent / "vectors" / "rights-keys").glob("[!_]*.json"))


def _key_context():
    ctx = json.loads((Path(__file__).parent / "vectors" / "rights-keys" / "_context.json").read_text())
    roots = {
        rid: keys.Root(contract._b64url(r["public_key"]), contract._ts(r["not_after"]))
        for rid, r in ctx["roots"].items()
    }
    return ctx, roots


def test_key_vector_context_matches_constants():
    ctx, _ = _key_context()
    assert ctx["max_key_lifetime_seconds"] == int(keys.MAX_KEY_LIFETIME.total_seconds())


@pytest.mark.parametrize("path", KEY_VECTORS, ids=lambda p: p.stem)
def test_key_vector(path):
    _, roots = _key_context()
    v = json.loads(path.read_text())
    now = contract._ts(v["now"])
    try:
        if v["kind"] == "certificate":
            keys.verify_certificate(v["raw"].encode(), roots=roots, tenant_id=v["tenant_id"], now=now)
        else:
            prev = v["previous"]
            previous = keys.Revocations(v["tenant_id"], prev["sequence"], frozenset(prev["revoked"]),
                                        prev["digest"]) if prev else None
            keys.verify_revocations(v["raw"].encode(), roots=roots, tenant_id=v["tenant_id"], now=now,
                                    previous=previous)
        outcome = {"ok": True}
    except keys.KeyRejected as exc:
        outcome = {"ok": False, "reason": exc.reason}
    assert outcome == v["expect"], v["name"]
