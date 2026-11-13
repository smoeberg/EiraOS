"""Trusted path for consent (GATE-KERNEL bilag A pkt. 1).

A session's uid says *which user* is on the socket, but every program the
user runs has that uid. Consent and confirmation must come from the consent
agent, so they carry a proof only it can make:

    proof = HMAC-SHA256(consent_key,
                        "EIRA-CONSENT-V1" 0 verb 0 uid 0 session 0 action 0 content_hash 0 rendering_hash)

- `consent_key` is 32 random bytes created by identityd with the session at
  login (``new_key``). It is kept in RAM only, tied to the current boot
  (``app/consent_keys.py``: a tmpfs store under /run/eira, never the session
  row on /data), and deleted at logout. On an installed system the only
  process that gets it is the registered consent agent, ``eira-consent-agent``
  (``app/auth/consent_agent.py``): identityd hands it over after checking the
  agent's GID ``eira-consent`` and that its windows are on the session's own
  compositor. The app's webview never holds the key, and on an installed
  system neither does its Rust core: the agent computes the proof itself,
  after showing the gate's rendering in its own window (EIRA-CONSENT-AGENT
  §5.2–§5.3). Only a development machine (not ``installed()``, the same
  condition as mock login) returns the key to the app at login.
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
