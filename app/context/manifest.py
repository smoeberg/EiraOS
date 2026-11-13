"""Manifests (EIRA-CONTEXT §6.3) and the encrypted context record (§2).

A manifest is canonical JSON (devices.canonical), sealed like a block with
label "eira-ctx-manifest-v2" and name "<device_id>/<seq>", then signed:

    stored = len(sig) as 2 bytes big-endian || sig || sealed
    sig    = DER ECDSA-P256-SHA256 by the device's signing key over ``sealed``

Merkle root over the manifest's block ids, in order (every file's blocks in
file order, then every document's blocks): leaf = SHA-256(0x00 || id bytes),
node = SHA-256(0x01 || left || right), an odd node is carried up unchanged;
the root of no blocks is SHA-256 of the empty string. Hex, lowercase.

The context record (``<prefix>/context``) is sealed with label
"eira-ctx-record-v2" and name "context".

Opening a manifest never raises for a bad manifest: it is ignored and
audited (M-1), so one forged object cannot stop a sync.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ec

from app.context.blocks import BLOCK_ID, Context, seal, unseal
from app.context.devices import Audit, DeviceList, canonical, device_id_of, sign, verify
from app.context.errors import E_CONTEXT_INTEGRITY, ContextError

MANIFEST_LABEL = "eira-ctx-manifest-v2"
RECORD_LABEL = "eira-ctx-record-v2"
MANIFEST_KEYS = {"eira_manifest", "context_id", "device_id", "seq", "parents", "issued_at",
                 "files", "documents", "merkle_root"}
FILE_KEYS = {"path", "blocks", "size", "mtime", "deleted"}
DOCUMENT_KEYS = {"id", "automerge_heads", "blocks"}
DEVICE_ID = re.compile(r"^[0-9a-f]{64}$")


def merkle_root(block_ids: list[str]) -> str:
    level = [sha256(b"\x00" + bytes.fromhex(b)).digest() for b in block_ids]
    if not level:
        return sha256(b"").hexdigest()
    while len(level) > 1:
        nxt = [sha256(b"\x01" + level[i] + level[i + 1]).digest() for i in range(0, len(level) - 1, 2)]
        if len(level) % 2:
            nxt.append(level[-1])
        level = nxt
    return level[0].hex()


def manifest_block_ids(manifest: dict[str, Any]) -> list[str]:
    ids = [b for f in manifest.get("files", []) for b in f.get("blocks", [])]
    ids += [b for d in manifest.get("documents", []) for b in d.get("blocks", [])]
    return ids


def safe_path(path: Any) -> bool:
    """A relative path inside the context: no absolute path, no "..", no
    empty or dot segments, no backslash or NUL. Readers must refuse others."""
    if not isinstance(path, str) or not path or path.startswith("/"):
        return False
    if "\\" in path or "\x00" in path:
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


def _check_shape(manifest: dict[str, Any]) -> None:
    """Exactly the contract's fields (§6.3): nothing only EiraOS understands
    (X-1) and nothing that could carry a local UID (U-1)."""
    if set(manifest) != MANIFEST_KEYS or manifest["eira_manifest"] != "1":
        raise ContextError(E_CONTEXT_INTEGRITY, "manifest fields")
    if not isinstance(manifest["seq"], int) or manifest["seq"] < 1:
        raise ContextError(E_CONTEXT_INTEGRITY, "manifest seq")
    for entry in manifest["files"]:
        if set(entry) != FILE_KEYS or not safe_path(entry["path"]):
            raise ContextError(E_CONTEXT_INTEGRITY, "manifest file entry")
    for entry in manifest["documents"]:
        if set(entry) != DOCUMENT_KEYS:
            raise ContextError(E_CONTEXT_INTEGRITY, "manifest document entry")
    for block_id in manifest_block_ids(manifest):
        if not isinstance(block_id, str) or not BLOCK_ID.match(block_id):
            raise ContextError(E_CONTEXT_INTEGRITY, "manifest block id")


def manifest_name(device_id: str, seq: int) -> str:
    return f"{device_id}/{seq}"


def seal_manifest(manifest: dict[str, Any], context: Context, signer: ec.EllipticCurvePrivateKey) -> bytes:
    """Fills in ``merkle_root``, then encrypts and signs. The device and
    context in the manifest must be the signer's and this context's."""
    manifest = {**manifest, "merkle_root": merkle_root(manifest_block_ids(manifest))}
    _check_shape(manifest)
    if manifest["context_id"] != context.context_id:
        raise ContextError(E_CONTEXT_INTEGRITY, "manifest for another context")
    if manifest["device_id"] != device_id_of(signer.public_key()):
        raise ContextError(E_CONTEXT_INTEGRITY, "manifest for another device")
    sealed = seal(context, MANIFEST_LABEL, manifest_name(manifest["device_id"], manifest["seq"]),
                  canonical(manifest))
    signature = sign(signer, sealed)
    return len(signature).to_bytes(2, "big") + signature + sealed


def open_manifest(
    device_id: str,
    seq: int,
    stored: bytes,
    context: Context,
    devices: DeviceList,
    audit: Audit,
) -> dict[str, Any] | None:
    """The manifest at ``manifests/<device_id>/<seq>``, or None if it must be
    ignored: an unknown device, a bad signature, a failed decryption, a
    manifest that does not match its path, or a wrong Merkle root. Every
    ignored manifest is audited (M-1)."""
    name = manifest_name(device_id, seq)

    def ignore(reason: str) -> None:
        audit("context.manifest_ignored", {"context_id": context.context_id, "manifest": name,
                                           "reason": reason})

    key = devices.key_of(device_id) if DEVICE_ID.match(device_id) else None
    if key is None:
        return ignore("unknown_device")
    if len(stored) < 2:
        return ignore("malformed")
    size = int.from_bytes(stored[:2], "big")
    signature, sealed = stored[2 : 2 + size], stored[2 + size :]
    if not verify(key, signature, sealed):
        return ignore("bad_signature")
    try:
        manifest = json.loads(unseal(context, MANIFEST_LABEL, name, sealed))
        _check_shape(manifest)
    except (ContextError, ValueError):
        return ignore("integrity")
    if (manifest["context_id"], manifest["device_id"], manifest["seq"]) != (context.context_id, device_id, seq):
        return ignore("does_not_match_its_path")
    if manifest["merkle_root"] != merkle_root(manifest_block_ids(manifest)):
        return ignore("merkle_root")
    return manifest


def seal_record(record: dict[str, Any], context: Context) -> bytes:
    if record.get("context_id") != context.context_id:
        raise ContextError(E_CONTEXT_INTEGRITY, "record for another context")
    return seal(context, RECORD_LABEL, "context", canonical(record))


def open_record(sealed: bytes, context: Context) -> dict[str, Any]:
    return json.loads(unseal(context, RECORD_LABEL, "context", sealed))
