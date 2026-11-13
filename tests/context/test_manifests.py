"""M-1 (EIRA-CONTEXT §6.3, §8; testplan §4), level N1, and the manifest vectors."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from app.context.blocks import Context, seal
from app.context.devices import DeviceList, accept_device_list, canonical, load_public, make_device_list
from app.context.errors import ContextError
from app.context.home import ContextWriter
from app.context.manifest import MANIFEST_LABEL, merkle_root, open_manifest, seal_manifest
from tests.context.conftest import ISSUED

VECTORS = Path(__file__).resolve().parents[1] / "vectors" / "context"


def _parts(name: str) -> tuple[str, int]:
    device_id, seq = name.split("/")
    return device_id, int(seq)


def _open(home, ctx, devices, audit, name, stored=None):
    device_id, seq = _parts(name)
    return open_manifest(device_id, seq, stored if stored is not None else home.get(f"manifests/{name}"),
                         ctx, devices, audit)


def test_a_valid_manifest_opens_and_nothing_is_audited(written, home, ctx, audit):
    _, name, devices = written
    manifest = _open(home, ctx, devices, audit, name)
    assert [f["path"] for f in manifest["files"]] == ["Referater/a.txt", "b.bin"]
    assert audit.events == []


def test_m1_a_a_device_not_on_the_list_is_ignored_and_audited(written, home, ctx, audit):
    _, name, _ = written
    stranger = ec.generate_private_key(ec.SECP256R1())
    other_list = make_device_list(ctx.context_id, 1, [(stranger.public_key(), "file")], stranger, issued_at=ISSUED)
    devices = accept_device_list(other_list, context_id=ctx.context_id, current=None, org_key=None, audit=audit)
    assert _open(home, ctx, devices, audit, name) is None
    assert audit.events[-1][0] == "context.manifest_ignored"
    assert audit.events[-1][1]["reason"] == "unknown_device"


def test_m1_b_a_removed_block_with_the_old_merkle_root_is_ignored_and_audited(written, home, ctx, device, audit):
    writer, name, devices = written
    manifest = _open(home, ctx, devices, audit, name)
    tampered = {**manifest, "files": [{**manifest["files"][0], "blocks": []}, manifest["files"][1]]}
    # Signed by the listed device, but with the old root: a block left out.
    sealed = seal(ctx, MANIFEST_LABEL, name, canonical(tampered))
    signature = device.sign(sealed, ec.ECDSA(hashes.SHA256()))
    stored = len(signature).to_bytes(2, "big") + signature + sealed
    assert _open(home, ctx, devices, audit, name, stored) is None
    assert audit.events[-1][1]["reason"] == "merkle_root"


def test_m1_c_a_changed_byte_after_signing_is_ignored_and_audited(written, home, ctx, audit):
    _, name, devices = written
    stored = bytearray(home.get(f"manifests/{name}"))
    stored[-5] ^= 0x01
    assert _open(home, ctx, devices, audit, name, bytes(stored)) is None
    assert audit.events[-1][1]["reason"] == "bad_signature"


def test_a_manifest_under_another_path_is_ignored(written, home, ctx, device, audit):
    writer, name, devices = written
    device_id, _ = _parts(name)
    # A validly signed manifest 1 presented as manifest 2.
    assert open_manifest(device_id, 2, home.get(f"manifests/{name}"), ctx, devices, audit) is None
    assert audit.events[-1][1]["reason"] in ("integrity", "does_not_match_its_path")


def test_m1_e_a_device_list_signed_without_right_is_rejected_and_the_old_one_stays(ctx, device, audit):
    first = make_device_list(ctx.context_id, 1, [(device.public_key(), "tpm")], device, issued_at=ISSUED)
    current = accept_device_list(first, context_id=ctx.context_id, current=None, org_key=None, audit=audit)
    intruder = ec.generate_private_key(ec.SECP256R1())
    forged = make_device_list(ctx.context_id, 2, [(device.public_key(), "tpm"), (intruder.public_key(), "tpm")],
                              intruder, issued_at=ISSUED)
    after = accept_device_list(forged, context_id=ctx.context_id, current=current, org_key=None, audit=audit)
    assert after is current
    assert audit.events[-1] == ("context.device_list_rejected",
                                {"context_id": ctx.context_id, "reason": "signer_without_right"})


def test_m1_e_an_organisation_list_needs_the_organisation_key(ctx, device, audit):
    org = ec.generate_private_key(ec.SECP256R1())
    by_device = make_device_list(ctx.context_id, 1, [(device.public_key(), "tpm")], device, issued_at=ISSUED)
    assert accept_device_list(by_device, context_id=ctx.context_id, current=None, org_key=org.public_key(),
                              audit=audit) is None
    by_org = make_device_list(ctx.context_id, 1, [(device.public_key(), "tpm")], org, signer_is_org=True,
                              issued_at=ISSUED)
    assert accept_device_list(by_org, context_id=ctx.context_id, current=None, org_key=org.public_key(),
                              audit=audit) is not None


def test_a_device_list_cannot_go_back_in_version(ctx, device, audit):
    two = make_device_list(ctx.context_id, 2, [(device.public_key(), "tpm")], device, issued_at=ISSUED)
    current = accept_device_list(two, context_id=ctx.context_id, current=None, org_key=None, audit=audit)
    one = make_device_list(ctx.context_id, 1, [(device.public_key(), "tpm")], device, issued_at=ISSUED)
    assert accept_device_list(one, context_id=ctx.context_id, current=current, org_key=None, audit=audit) is current


def test_a_second_manifest_at_the_same_path_is_refused(home, ctx, device):
    """H-1 for the local home: an existing manifest is never overwritten."""
    first = ContextWriter(home, ctx, device)
    first.add_file("x", b"1")
    name = first.commit()
    before = home.get(f"manifests/{name}")
    second = ContextWriter(home, ctx, device)  # does not know seq 1 exists
    second.add_file("x", b"2")
    with pytest.raises(ContextError):
        second.commit()
    assert home.get(f"manifests/{name}") == before


def test_a_block_already_in_the_home_is_kept(home, ctx, device):
    writer = ContextWriter(home, ctx, device)
    writer.add_file("a", b"same")
    block = writer.files["a"]["blocks"][0]
    stored = home.get(f"blocks/{block[:2]}/{block}")
    writer.add_file("b", b"same")  # a fresh, different ciphertext of the same block
    assert home.get(f"blocks/{block[:2]}/{block}") == stored


def test_merkle_root_construction():
    import hashlib

    a, b, c = (hashlib.sha256(x).hexdigest() for x in (b"a", b"b", b"c"))
    leaf = [hashlib.sha256(b"\x00" + bytes.fromhex(x)).digest() for x in (a, b, c)]
    ab = hashlib.sha256(b"\x01" + leaf[0] + leaf[1]).digest()
    assert merkle_root([a, b, c]) == hashlib.sha256(b"\x01" + ab + leaf[2]).hexdigest()
    assert merkle_root([]) == hashlib.sha256(b"").hexdigest()
    assert merkle_root([a, b]) != merkle_root([b, a])  # order matters: nothing can be swapped


def test_manifest_vector_opens_with_eiraos(audit):
    v = json.loads((VECTORS / "manifest-v2.json").read_text())
    ctx = Context(v["context_id"], bytes.fromhex(v["cmk"]))
    devices = DeviceList(v["context_id"], 1, {v["device_id"]: load_public(v["device_public_key"])})
    manifest = open_manifest(v["device_id"], v["seq"], bytes.fromhex(v["stored"]), ctx, devices, audit)
    assert manifest == v["manifest"]
    assert base64.b64decode(v["device_public_key"])


def test_seal_manifest_refuses_another_device_or_context(ctx, device):
    other = ec.generate_private_key(ec.SECP256R1())
    from app.context.devices import device_id_of

    manifest = {"eira_manifest": "1", "context_id": ctx.context_id, "device_id": device_id_of(other.public_key()),
                "seq": 1, "parents": [], "issued_at": ISSUED, "files": [], "documents": [], "merkle_root": ""}
    with pytest.raises(ContextError):
        seal_manifest(manifest, ctx, device)
