#!/usr/bin/env python3
"""eira-context-export: read an EIRA context home without EiraOS.

The exit guarantee of EIRA-CONTEXT 1.0 §6.5. This file is the reference
reader of the storage format (§6). It deliberately imports nothing from
EiraOS: only the Python standard library and ``cryptography``. If EiraOS ever
writes something this tool cannot read, the exit guarantee is broken (X-1).

Usage:
    eira_context_export.py --home DIR --cmk-file FILE --out DIR [--org-key PEM]

The CMK file holds the context's 32-byte master key, raw or as 64 hex
characters. Output:
    OUT/context.json             the context record
    OUT/files/<path>             every file, as of each device's newest manifest
    OUT/files/<path>.konflikt-<device>  other versions of a file changed on
                                 several devices (nothing is silently dropped)
    OUT/documents/<id>.automerge structured data in Automerge's own format
    OUT/export.json              what was exported, and what was ignored and why

Exit status: 0 on success, 1 if anything failed verification (it is reported
in export.json and not written), 2 on usage errors.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import sys
from pathlib import Path

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class Integrity(Exception):
    pass


def hkdf(cmk: bytes, salt: bytes | None, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(cmk)


def unseal(cmk: bytes, context_id: str, label: str, name: str, data: bytes) -> bytes:
    # version(1) || salt(32) || nonce(12) || ChaCha20-Poly1305 ciphertext+tag
    if len(data) < 1 + 32 + 12 + 16 or data[0] != 2:
        raise Integrity("not a version 2 object")
    salt, nonce = data[1:33], data[33:45]
    key = hkdf(cmk, salt, (label + name).encode())
    try:
        return ChaCha20Poly1305(key).decrypt(nonce, data[45:], (label + context_id + name).encode())
    except InvalidTag:
        raise Integrity("authentication failed") from None


def read_block(home: Path, cmk: bytes, context_id: str, block_id: str) -> bytes:
    if len(block_id) != 64 or any(c not in "0123456789abcdef" for c in block_id):
        raise Integrity("malformed block id")
    plain = unseal(cmk, context_id, "eira-ctx-block-v2", block_id,
                   (home / "blocks" / block_id[:2] / block_id).read_bytes())
    id_key = hkdf(cmk, None, b"eira-ctx-blockid-v1")
    if not hmac.compare_digest(hmac.new(id_key, plain, hashlib.sha256).hexdigest(), block_id):
        raise Integrity("block id does not match content")
    return plain


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def load_key(b64: str) -> ec.EllipticCurvePublicKey:
    der = base64.b64decode(b64)
    key = serialization.load_der_public_key(der)
    if not isinstance(key, ec.EllipticCurvePublicKey):
        raise Integrity("not an EC key")
    return key


def verify(key: ec.EllipticCurvePublicKey, sig: bytes, data: bytes) -> bool:
    try:
        key.verify(sig, data, ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False


def merkle(ids: list[str]) -> str:
    level = [hashlib.sha256(b"\x00" + bytes.fromhex(i)).digest() for i in ids]
    if not level:
        return hashlib.sha256(b"").hexdigest()
    while len(level) > 1:
        nxt = [hashlib.sha256(b"\x01" + level[i] + level[i + 1]).digest() for i in range(0, len(level) - 1, 2)]
        if len(level) % 2:
            nxt.append(level[-1])
        level = nxt
    return level[0].hex()


def safe(path) -> bool:
    return (isinstance(path, str) and path and not path.startswith("/") and "\\" not in path
            and "\x00" not in path and all(p not in ("", ".", "..") for p in path.split("/")))


def devices(home: Path, org_key: ec.EllipticCurvePublicKey | None) -> tuple[str, dict]:
    envelope = json.loads((home / "keys" / "devices.signed").read_bytes())
    body = envelope["list"]
    keys = {}
    for entry in body["devices"]:
        key = load_key(entry["public_key"])
        der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        if hashlib.sha256(der).hexdigest() != entry["device_id"]:
            raise Integrity("device id is not the key's fingerprint")
        keys[entry["device_id"]] = key
    signer = org_key if envelope["signer"] == "org" else keys.get(envelope["signer"])
    if signer is None:
        raise Integrity("device list: signer unknown (an organisation list needs --org-key)")
    if not verify(signer, base64.b64decode(envelope["signature"]), canonical(body)):
        raise Integrity("device list: bad signature")
    return body["context_id"], keys


def newest_manifests(home: Path, cmk: bytes, context_id: str, keys: dict, ignored: list) -> dict:
    newest = {}
    root = home / "manifests"
    for device_dir in sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []:
        device_id = device_dir.name
        key = keys.get(device_id)
        for path in sorted(device_dir.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else -1):
            name = f"{device_id}/{path.name}"
            if key is None or not path.name.isdigit():
                ignored.append({"manifest": name, "reason": "unknown_device"})
                continue
            raw = path.read_bytes()
            size = int.from_bytes(raw[:2], "big")
            sig, sealed = raw[2:2 + size], raw[2 + size:]
            if not verify(key, sig, sealed):
                ignored.append({"manifest": name, "reason": "bad_signature"})
                continue
            try:
                m = json.loads(unseal(cmk, context_id, "eira-ctx-manifest-v2", name, sealed))
            except (Integrity, ValueError):
                ignored.append({"manifest": name, "reason": "integrity"})
                continue
            ids = [b for f in m["files"] for b in f["blocks"]] + [b for d in m["documents"] for b in d["blocks"]]
            if (m["context_id"], m["device_id"], m["seq"]) != (context_id, device_id, int(path.name)) \
                    or m["merkle_root"] != merkle(ids):
                ignored.append({"manifest": name, "reason": "integrity"})
                continue
            if device_id not in newest or m["seq"] > newest[device_id]["seq"]:
                newest[device_id] = m
    return newest


def export(home: Path, cmk: bytes, out: Path, org_key=None) -> dict:
    context_id, keys = devices(home, org_key)
    report = {"context_id": context_id, "files": [], "documents": [], "ignored": [], "failed": []}
    record = json.loads(unseal(cmk, context_id, "eira-ctx-record-v2", "context", (home / "context").read_bytes()))
    out.mkdir(parents=True, exist_ok=True)
    (out / "context.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    newest = newest_manifests(home, cmk, context_id, keys, report["ignored"])
    versions: dict[str, list[tuple[str, dict]]] = {}
    for device_id in sorted(newest):
        for entry in newest[device_id]["files"]:
            if entry["deleted"]:
                continue
            same = [v for v in versions.get(entry["path"], []) if v[1]["blocks"] == entry["blocks"]]
            if not same:
                versions.setdefault(entry["path"], []).append((device_id, entry))

    for path, found in sorted(versions.items()):
        for index, (device_id, entry) in enumerate(found):
            target = path if index == 0 else f"{path}.konflikt-{device_id[:12]}"
            if not safe(path):
                report["failed"].append({"path": path, "reason": "unsafe path"})
                continue
            try:
                data = b"".join(read_block(home, cmk, context_id, b) for b in entry["blocks"])
                if len(data) != entry["size"]:
                    raise Integrity("size differs from the manifest")
            except (Integrity, OSError) as exc:
                report["failed"].append({"path": path, "reason": str(exc)})
                continue
            dest = out / "files" / target
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            report["files"].append({"path": target, "size": len(data), "device": device_id})

    for device_id in sorted(newest):
        for doc in newest[device_id]["documents"]:
            if not safe(doc["id"]):
                report["failed"].append({"document": doc["id"], "reason": "unsafe id"})
                continue
            data = b"".join(read_block(home, cmk, context_id, b) for b in doc["blocks"])
            dest = out / "documents" / f"{doc['id']}.automerge"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            report["documents"].append({"id": doc["id"], "device": device_id})

    (out / "export.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--cmk-file", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--org-key", type=Path, help="organisation public key (PEM) for an organisation context")
    args = parser.parse_args(argv)
    raw = args.cmk_file.read_bytes().strip()
    cmk = bytes.fromhex(raw.decode()) if len(raw) == 64 else raw
    if len(cmk) != 32:
        print("the CMK is 32 bytes (raw or 64 hex characters)", file=sys.stderr)
        return 2
    org_key = serialization.load_pem_public_key(args.org_key.read_bytes()) if args.org_key else None
    try:
        report = export(args.home, cmk, args.out, org_key)
    except (Integrity, OSError, KeyError, ValueError) as exc:
        print(f"export failed: {exc}", file=sys.stderr)
        return 1
    print(f"{len(report['files'])} files, {len(report['documents'])} documents to {args.out}; "
          f"{len(report['ignored'])} manifests ignored, {len(report['failed'])} failed")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
