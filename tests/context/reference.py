"""Independent reference implementation of EIRA-CONTEXT §6.2/§6.3 for tests.

Written directly against ``cryptography`` from the contract's text, without
importing app.context: it produces the test vectors (testplan §3) and checks
EiraOS' output the other way. Unlike the product API, it takes salt, nonce
and block_id from the caller, so it can build vectors and broken writers.
"""

from __future__ import annotations

import hashlib
import hmac

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

BLOCK = "eira-ctx-block-v2"
MANIFEST = "eira-ctx-manifest-v2"


def hkdf(cmk: bytes, salt: bytes | None, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(cmk)


def block_id(cmk: bytes, plaintext: bytes) -> str:
    return hmac.new(hkdf(cmk, None, b"eira-ctx-blockid-v1"), plaintext, hashlib.sha256).hexdigest()


def seal(cmk: bytes, context_id: str, label: str, name: str, plaintext: bytes,
         salt: bytes, nonce: bytes) -> bytes:
    key = hkdf(cmk, salt, (label + name).encode())
    aad = (label + context_id + name).encode()
    return b"\x02" + salt + nonce + ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)


def unseal(cmk: bytes, context_id: str, label: str, name: str, sealed: bytes) -> bytes:
    salt, nonce = sealed[1:33], sealed[33:45]
    key = hkdf(cmk, salt, (label + name).encode())
    return ChaCha20Poly1305(key).decrypt(nonce, sealed[45:], (label + context_id + name).encode())
