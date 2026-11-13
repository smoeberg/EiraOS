"""U-1: a Linux UID never leaves the device (EIRA-CONTEXT §1; testplan §4).

T-U1-a statically over every JSON schema in the repository, and the N1 part
of T-U1-b: with recognisable UIDs in the process, nothing the writer puts in
the home, and no decrypted manifest or record, contains them. The full
T-U1-b (Fleet, glimt, audit export) runs at N2/N3 when those exist.
"""

from __future__ import annotations

import json
import os
import struct
from pathlib import Path

import jsonschema
import pytest

from app.context.devices import make_device_list
from app.context.home import ContextWriter
from app.context.manifest import open_manifest, open_record
from tests.context.conftest import ISSUED

REPO = Path(__file__).resolve().parents[2]
SCHEMAS = REPO / "specs" / "schemas"
FORBIDDEN = {"uid", "gid"}
UIDS = (87654, 87655)


def _schema_files() -> list[Path]:
    skip = {"node_modules", "target", ".git"}
    return [p for p in REPO.rglob("*.schema.json") if not skip & set(p.parts)]


def _property_names(node, found: set[str]) -> None:
    if isinstance(node, dict):
        for key in ("properties", "patternProperties"):
            for name, sub in (node.get(key) or {}).items():
                found.add(name.lower())
                _property_names(sub, found)
        for value in node.values():
            _property_names(value, found)
    elif isinstance(node, list):
        for value in node:
            _property_names(value, found)


@pytest.mark.parametrize("path", _schema_files(), ids=lambda p: str(p.relative_to(REPO)))
def test_u1_a_no_schema_has_a_uid_field(path):
    names: set[str] = set()
    _property_names(json.loads(path.read_text(encoding="utf-8")), names)
    bad = {n for n in names if n in FORBIDDEN or n.endswith("_uid") or n.endswith("_gid")}
    assert not bad, bad


def test_u1_a_the_context_schemas_exist_and_are_closed():
    for name in ("eira-context-manifest-1", "eira-context-devices-1", "eira-context-record-1"):
        schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False


def _encodings(uid: int) -> list[bytes]:
    return [str(uid).encode(), format(uid, "x").encode(), format(uid, "X").encode(),
            struct.pack(">I", uid), struct.pack("<I", uid)]


def test_u1_b_n1_no_uid_in_anything_written_or_decrypted(home, ctx, device, audit, monkeypatch):
    monkeypatch.setattr(os, "getuid", lambda: UIDS[0])
    monkeypatch.setattr(os, "geteuid", lambda: UIDS[0])
    monkeypatch.setattr(os, "getgid", lambda: UIDS[1])
    writer = ContextWriter(home, ctx, device)
    record = {"eira_context": "1", "context_id": ctx.context_id, "display_name": "Bestyrelse", "kind": "personal"}
    writer.write_record(record)
    writer.add_file("Referater/a.txt", b"referat")
    name = writer.commit()
    home.put_if_absent("keys/devices.signed",
                       make_device_list(ctx.context_id, 1, [(device.public_key(), "file")], device, issued_at=ISSUED))

    from app.context.devices import accept_device_list

    devices = accept_device_list(home.get("keys/devices.signed"), context_id=ctx.context_id, current=None,
                                 org_key=None, audit=audit)
    device_id, seq = name.split("/")
    manifest = open_manifest(device_id, int(seq), home.get(f"manifests/{name}"), ctx, devices, audit)
    jsonschema.validate(manifest, json.loads((SCHEMAS / "eira-context-manifest-1.schema.json").read_text()))
    jsonschema.validate(open_record(home.get("context"), ctx),
                        json.loads((SCHEMAS / "eira-context-record-1.schema.json").read_text()))

    decrypted = [json.dumps(manifest).encode(), json.dumps(open_record(home.get("context"), ctx)).encode()]
    stored = [p.read_bytes() for p in home.root.rglob("*") if p.is_file()]
    for uid in UIDS:
        for data in decrypted:
            for pattern in _encodings(uid):
                assert pattern not in data, (uid, pattern)
        # Stored objects are ciphertext (random) or the plaintext device list.
        # A 4-byte binary form can occur by chance in random bytes; five ASCII
        # digits practically cannot, and the readable form is what a bug writes.
        for data in stored:
            assert str(uid).encode() not in data, uid
    assert all(p.relative_to(home.root).parts[0] in {"context", "keys", "blocks", "manifests"}
               for p in home.root.rglob("*") if p.is_file())
