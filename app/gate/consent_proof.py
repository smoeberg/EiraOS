"""Trusted path for consent (GATE-KERNEL bilag A pkt. 1).

A session's uid says *which user* is on the socket, but every program the
user runs has that uid. Consent and confirmation must come from the EiraOS
desktop app itself, so they carry a proof only it can make:

    proof = HMAC-SHA256(consent_key,
                        "EIRA-CONSENT-V1" 0 verb 0 uid 0 session 0 action 0 content_hash 0 rendering_hash)

- `consent_key` is 32 random bytes created with the session at login and
  returned only to the process that completed the login (the app's Rust
  core). It lives there in memory and in the session row (/data, readable
  only by the service user). It never reaches the webview or a file another
  process could read; Yama ptrace protection keeps other same-uid programs
  out of the app's memory.
- The proof is bound to the verb, the uid, the session, the action, its
  content and the exact rendering the user saw: it cannot be reused for
  another action, another step or another user, nor replayed (consent and
  confirmation are single-use in the gate anyway).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

DOMAIN = b"EIRA-CONSENT-V1"
# "delegate": the user lets the model prepare actions (app/auth/delegation.py);
# action_id is then the delegation proposal id.
VERBS = frozenset({"consent", "confirm", "delegate"})
KEY_BYTES = 32


def new_key() -> str:
    return secrets.token_hex(KEY_BYTES)


def message(verb: str, uid: int, session_id: str, action_id: str, content_hash: str, rendering_hash: str) -> bytes:
    if verb not in VERBS:
        raise ValueError(f"unknown verb {verb!r}")
    parts = [DOMAIN, verb.encode(), str(uid).encode(), session_id.encode(), action_id.encode(),
             content_hash.encode(), rendering_hash.encode()]
    if any(b"\0" in part for part in parts):
        raise ValueError("NUL in consent proof field")
    return b"\0".join(parts)


def compute(key_hex: str, verb: str, uid: int, session_id: str, action_id: str,
            content_hash: str, rendering_hash: str) -> str:
    key = bytes.fromhex(key_hex)
    return hmac.new(key, message(verb, uid, session_id, action_id, content_hash, rendering_hash),
                    hashlib.sha256).hexdigest()


def verify(key_hex: str | None, proof: str | None, verb: str, uid: int, session_id: str,
           action_id: str, content_hash: str, rendering_hash: str) -> bool:
    if not key_hex or not isinstance(proof, str) or len(proof) != 64:
        return False
    try:
        expected = compute(key_hex, verb, uid, session_id, action_id, content_hash, rendering_hash)
    except ValueError:
        return False
    return hmac.compare_digest(expected, proof)
