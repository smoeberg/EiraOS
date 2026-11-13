"""A context home on a local directory, and writing a context into it
(EIRA-CONTEXT §6.1, §7 "Skrive").

The home is "dumb" storage: objects are only ever added (append-only), and
an object that exists is never overwritten (H-1). Here that is ``O_EXCL``;
S3 and WebDAV homes (``If-None-Match: *``) come with F2.2 behind the same
two methods.

Layout under the home's root (the context's pseudonymous prefix):

    context                     sealed context record
    keys/devices.signed         signed device list
    blocks/<first 2 hex>/<block_id>
    manifests/<device_id>/<seq>
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ec

from app.context.blocks import Context, encrypt_block
from app.context.chunking import chunks
from app.context.devices import device_id_of
from app.context.errors import E_CONTEXT_INTEGRITY, ContextError
from app.context.manifest import safe_path, seal_manifest, seal_record


def block_path(block_id: str) -> str:
    return f"blocks/{block_id[:2]}/{block_id}"


class LocalHome:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)

    def put_if_absent(self, name: str, data: bytes) -> bool:
        """True if written, False if the object already existed (unchanged)."""
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return False
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        return True

    def get(self, name: str) -> bytes:
        return (self.root / name).read_bytes()

    def exists(self, name: str) -> bool:
        return (self.root / name).exists()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ContextWriter:
    """One device writing one context: blocks first, then the manifest (§7),
    so a failure leaves at most unused blocks."""

    home: LocalHome
    context: Context
    signer: ec.EllipticCurvePrivateKey
    seq: int = 0
    parents: list[str] = field(default_factory=list)
    files: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def device_id(self) -> str:
        return device_id_of(self.signer.public_key())

    def write_record(self, record: dict[str, Any]) -> None:
        self.home.put_if_absent("context", seal_record(record, self.context))

    def add_file(self, path: str, data: bytes, mtime: str | None = None) -> None:
        if not safe_path(path):
            raise ValueError(f"not a path inside the context: {path!r}")
        block_ids = []
        for piece in chunks(data):
            block_id, block = encrypt_block(piece, self.context)
            # Already there (dedup, or another device): the first one stays.
            self.home.put_if_absent(block_path(block_id), block)
            block_ids.append(block_id)
        self.files[path] = {"path": path, "blocks": block_ids, "size": len(data),
                            "mtime": mtime or _now(), "deleted": False}

    def delete_file(self, path: str) -> None:
        entry = self.files.get(path)
        if entry is not None:
            self.files[path] = {**entry, "blocks": [], "size": 0, "deleted": True, "mtime": _now()}

    def commit(self) -> str:
        """Writes the next manifest; returns its name. A manifest that already
        exists at that name is never overwritten: E_CONTEXT_INTEGRITY."""
        seq = self.seq + 1
        manifest = {
            "eira_manifest": "1",
            "context_id": self.context.context_id,
            "device_id": self.device_id,
            "seq": seq,
            "parents": list(self.parents),
            "issued_at": _now(),
            "files": list(self.files.values()),
            "documents": [],
            "merkle_root": "",
        }
        name = f"{self.device_id}/{seq}"
        if not self.home.put_if_absent(f"manifests/{name}", seal_manifest(manifest, self.context, self.signer)):
            raise ContextError(E_CONTEXT_INTEGRITY, f"manifest {name} already exists")
        self.seq = seq
        self.parents = [name]
        return name
