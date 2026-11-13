"""Blocks (EIRA-CONTEXT §6.2): content-addressed, non-deterministic AEAD.

Byte encoding (§6.2 with the F2.1 precision): every string that enters a key
derivation or an AAD is UTF-8, concatenated without separators. ``block_id``
is 64 lowercase hex characters and ``context_id`` is ``ctx_`` plus 26 base32
characters, so the concatenation is unambiguous.

    block_id   = hex(HMAC-SHA256(K_id, plaintext))
    K_id       = HKDF-SHA256(CMK, salt=none, info="eira-ctx-blockid-v1")
    salt       = 32 random bytes, nonce = 12 random bytes  (fresh each time)
    block_key  = HKDF-SHA256(CMK, salt, info=label || name)
    aad        = label || context_id || name
    block      = 0x02 || salt || nonce || ChaCha20-Poly1305(block_key, nonce, plaintext, aad)

For a block, label is "eira-ctx-block-v2" and name is the block_id. The same
sealing is used for manifests and the context record with their own label
and name (manifest.py).
"""

from __future__ import annotations

import hmac
import os
import re
import secrets
from dataclasses import dataclass, field
from hashlib import sha256

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.context.errors import E_CONTEXT_INTEGRITY, ContextError

FORMAT_VERSION = 2
BLOCK_LABEL = "eira-ctx-block-v2"
BLOCK_ID_LABEL = "eira-ctx-blockid-v1"
SALT_SIZE = 32
NONCE_SIZE = 12
CMK_SIZE = 32
_HEADER = 1 + SALT_SIZE + NONCE_SIZE

CONTEXT_ID = re.compile(r"^ctx_[a-z2-7]{26}$")
BLOCK_ID = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Context:
    """An open context: its identity and its master key (§5.1)."""

    context_id: str
    cmk: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not CONTEXT_ID.match(self.context_id):
            raise ValueError("context_id must be ctx_ followed by 26 base32 characters")
        if len(self.cmk) != CMK_SIZE:
            raise ValueError("the CMK is 32 bytes")


def new_context_id() -> str:
    """``ctx_`` + 26 base32 characters (128 random bits, §1)."""
    alphabet = "abcdefghijklmnopqrstuvwxyz234567"
    value = secrets.randbits(130)  # 26 * 5 bits; the top two are random too
    chars = []
    for _ in range(26):
        chars.append(alphabet[value & 31])
        value >>= 5
    return "ctx_" + "".join(chars)


def _hkdf(cmk: bytes, salt: bytes | None, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(cmk)


def _block_id(plaintext: bytes, context: Context) -> str:
    id_key = _hkdf(context.cmk, None, BLOCK_ID_LABEL.encode())
    return hmac.new(id_key, plaintext, sha256).hexdigest()


def seal(context: Context, label: str, name: str, plaintext: bytes) -> bytes:
    """AEAD with fresh salt and nonce from the CSPRNG on every call (B-2)."""
    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    key = _hkdf(context.cmk, salt, (label + name).encode())
    aad = (label + context.context_id + name).encode()
    return bytes([FORMAT_VERSION]) + salt + nonce + ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)


def unseal(context: Context, label: str, name: str, sealed: bytes) -> bytes:
    """Opens what :func:`seal` wrote under the same label and name. Any
    change, and a wrong context or name, is ``E_CONTEXT_INTEGRITY``."""
    if len(sealed) < _HEADER + 16 or sealed[0] != FORMAT_VERSION:
        raise ContextError(E_CONTEXT_INTEGRITY, "not a version 2 sealed object")
    salt = sealed[1 : 1 + SALT_SIZE]
    nonce = sealed[1 + SALT_SIZE : _HEADER]
    key = _hkdf(context.cmk, salt, (label + name).encode())
    aad = (label + context.context_id + name).encode()
    try:
        return ChaCha20Poly1305(key).decrypt(nonce, sealed[_HEADER:], aad)
    except InvalidTag:
        raise ContextError(E_CONTEXT_INTEGRITY, "authentication failed") from None


def encrypt_block(plaintext: bytes, context: Context) -> tuple[str, bytes]:
    """Returns ``(block_id, block)``.

    B-1: the id is computed here, from exactly the plaintext encrypted here.
    The function takes nothing else: no id, salt, nonce or key from a caller.
    """
    block_id = _block_id(plaintext, context)
    return block_id, seal(context, BLOCK_LABEL, block_id, plaintext)


def decrypt_block(block_id: str, block: bytes, context: Context) -> bytes:
    """The plaintext, only if the block authenticates under this context and
    id *and* the id is the HMAC of the plaintext (§6.2, "Ved læsning")."""
    if not BLOCK_ID.match(block_id):
        raise ContextError(E_CONTEXT_INTEGRITY, "malformed block_id")
    plaintext = unseal(context, BLOCK_LABEL, block_id, block)
    if not hmac.compare_digest(_block_id(plaintext, context), block_id):
        raise ContextError(E_CONTEXT_INTEGRITY, "block_id does not match the content")
    return plaintext
