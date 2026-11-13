"""Writes the context test vectors (EIRA-CONTEXT testplan §3).

Run from the repository root: ``python3 tests/vectors/context/make_vectors.py``.
Everything comes from tests/context/reference.py (independent of
app.context) and fixed inputs, so the files are reproducible except the
ECDSA signature in manifest-v2.json, which is randomised by design and is
checked, not compared.
"""

from __future__ import annotations

import base64
import json
import sys
from hashlib import sha256
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tests.context import reference as ref  # noqa: E402

OUT = Path(__file__).resolve().parent
CMK = bytes(range(32))
CONTEXT_ID = "ctx_" + "abcdefghijklmnopqrstuvwxyz"
OTHER_CONTEXT_ID = "ctx_" + "zyxwvutsrqponmlkjihgfedcba"
PLAINTEXT = "Referat fra bestyrelsesmødet 20. november 2026. Æ, ø og å.\n".encode()
SALT = bytes([0x5A]) * 32
NONCE = bytes([0xA5]) * 12
# A fixed P-256 device key, so device_id is reproducible.
DEVICE_SCALAR = int.from_bytes(sha256(b"eira-ctx-test-device").digest(), "big") % (
    0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551)


def h(data: bytes) -> str:
    return data.hex()


def flip(data: bytes, index: int) -> bytes:
    return data[:index] + bytes([data[index] ^ 0x01]) + data[index + 1:]


def merkle(ids: list[str]) -> str:
    level = [sha256(b"\x00" + bytes.fromhex(i)).digest() for i in ids]
    if not level:
        return sha256(b"").hexdigest()
    while len(level) > 1:
        nxt = [sha256(b"\x01" + level[i] + level[i + 1]).digest() for i in range(0, len(level) - 1, 2)]
        if len(level) % 2:
            nxt.append(level[-1])
        level = nxt
    return level[0].hex()


def main() -> None:
    block_id = ref.block_id(CMK, PLAINTEXT)
    block = ref.seal(CMK, CONTEXT_ID, ref.BLOCK, block_id, PLAINTEXT, SALT, NONCE)
    (OUT / "block-v2.json").write_text(json.dumps({
        "cmk": h(CMK), "context_id": CONTEXT_ID, "plaintext": h(PLAINTEXT),
        "block_id": block_id, "salt": h(SALT), "nonce": h(NONCE), "block": h(block),
    }, indent=2) + "\n")

    tag_at = len(block) - 1
    wrong_id = ref.block_id(CMK, b"another plaintext")
    (OUT / "block-v2-negative.json").write_text(json.dumps({
        "cmk": h(CMK), "context_id": CONTEXT_ID, "block_id": block_id,
        "cases": [
            {"name": "version", "block_id": block_id, "context_id": CONTEXT_ID, "block": h(flip(block, 0))},
            {"name": "salt", "block_id": block_id, "context_id": CONTEXT_ID, "block": h(flip(block, 1))},
            {"name": "nonce", "block_id": block_id, "context_id": CONTEXT_ID, "block": h(flip(block, 33))},
            {"name": "ciphertext", "block_id": block_id, "context_id": CONTEXT_ID, "block": h(flip(block, 45))},
            {"name": "tag", "block_id": block_id, "context_id": CONTEXT_ID, "block": h(flip(block, tag_at))},
            {"name": "wrong_context_id", "block_id": block_id, "context_id": OTHER_CONTEXT_ID, "block": h(block)},
            {"name": "wrong_block_id", "block_id": wrong_id, "context_id": CONTEXT_ID, "block": h(block)},
            # T-B1-c: a broken writer encrypted P under an id that is not HMAC(P),
            # with the correct AAD for that id: AEAD succeeds, the HMAC check fails.
            {"name": "id_not_hmac_of_content", "block_id": wrong_id, "context_id": CONTEXT_ID,
             "block": h(ref.seal(CMK, CONTEXT_ID, ref.BLOCK, wrong_id, PLAINTEXT, SALT, NONCE))},
        ],
    }, indent=2) + "\n")

    key = ec.derive_private_key(DEVICE_SCALAR, ec.SECP256R1())
    der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    device_id = sha256(der).hexdigest()
    manifest = {
        "eira_manifest": "1", "context_id": CONTEXT_ID, "device_id": device_id, "seq": 1, "parents": [],
        "issued_at": "2026-11-13T12:00:00+00:00",
        "files": [{"path": "Referater/2026-11-20.txt", "blocks": [block_id], "size": len(PLAINTEXT),
                   "mtime": "2026-11-13T12:00:00+00:00", "deleted": False}],
        "documents": [], "merkle_root": merkle([block_id]),
    }
    name = f"{device_id}/1"
    body = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    sealed = ref.seal(CMK, CONTEXT_ID, ref.MANIFEST, name, body, SALT, NONCE)
    signature = key.sign(sealed, ec.ECDSA(hashes.SHA256()))
    (OUT / "manifest-v2.json").write_text(json.dumps({
        "cmk": h(CMK), "context_id": CONTEXT_ID, "device_id": device_id, "seq": 1,
        "device_public_key": base64.b64encode(der).decode(), "manifest": manifest,
        "stored": h(len(signature).to_bytes(2, "big") + signature + sealed),
        "block": h(block), "block_id": block_id,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
