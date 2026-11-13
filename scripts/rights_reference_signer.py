#!/usr/bin/env python3
"""Reference signer for the rights vectors (EIRA-RIGHTS-SET §3, §8).

Reads one JSON request per line on stdin and writes the canonical signed
document, one per line, on stdout. eira-fleet-control's signer must answer
the same requests with the same bytes (scripts/rights_vectors_conformance.py).

    {"kind": "rights_set" | "key_certificate" | "revocations",
     "seed_hex": "<32-byte Ed25519 seed, TEST KEYS ONLY>",
     "document": {..., "signature": {"alg": "ed25519", "key_id": "..."}}}
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from app.rights import contract, keys  # noqa: E402

SIGNING_INPUT = {
    "rights_set": contract.signing_input,
    "key_certificate": keys.signing_input_certificate,
    "revocations": keys.signing_input_revocations,
}


def sign(request: dict) -> bytes:
    document = request["document"]
    message = SIGNING_INPUT[request["kind"]](document)
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(request["seed_hex"]))
    value = base64.urlsafe_b64encode(key.sign(message)).rstrip(b"=").decode()
    signed = {**document, "signature": {**document["signature"], "value": value}}
    return contract.canonical(signed)


def main() -> int:
    for line in sys.stdin:
        if line.strip():
            sys.stdout.buffer.write(sign(json.loads(line)) + b"\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
