"""Callers for gate tests (bilag A pkt. 1). Production callers come from
SO_PEERCRED; tests set them explicitly, like the IPC layer does."""

from __future__ import annotations

from app.gate.caller import Caller

HUMAN_UID = 1000
HUMAN = Caller(uid=HUMAN_UID, pid=4242, model=False)
OTHER_HUMAN = Caller(uid=1001, pid=4343, model=False)
MODEL = Caller(uid=990, pid=4444, model=True)

# What an authenticated login leaves in the session store, for HUMAN_UID.
# expires_at is always written by create_session_from_claims; the gate fails
# closed on a session without it.
HUMAN_SESSION = {
    "authenticated_at": "2026-11-09T06:00:00Z",
    "expires_at": "2099-01-01T00:00:00Z",
    "os_uid": HUMAN_UID,
}


class Peer:
    """Stand-in for PeerCredentials as the daemon server passes it."""

    def __init__(self, caller: Caller):
        self.uid, self.pid, self.gid, self.groups = caller.uid, caller.pid, caller.uid, frozenset()

# The consent key an authenticated login hands to the app (consent_proof.py).
CONSENT_KEY = "11" * 32
HUMAN_SESSION["consent_key"] = CONSENT_KEY


class ProvingGate:
    """Stands in for the EiraOS app: holds the session's consent key and adds
    the proof to consent/confirm for the current caller, as the app's Rust
    core does. Tests of the proof rules themselves use the bare gate."""

    def __init__(self, gate, sessions):
        self._gate = gate
        self._sessions = sessions

    def __getattr__(self, name):
        return getattr(self._gate, name)

    def __setattr__(self, name, value):
        if name in ("_gate", "_sessions"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._gate, name, value)

    def _prove(self, verb, action_id, content_hash, rendering_hash, session_id):
        from app.gate import consent_proof
        from app.gate.caller import current

        session = self._sessions(session_id) if session_id else None
        caller = current()
        if not session or not session.get("consent_key") or caller is None:
            return None
        return consent_proof.compute(session["consent_key"], verb, caller.uid, session_id,
                                     action_id, content_hash, rendering_hash)

    def grant_consent(self, action_id, content_hash, rendering_hash, session_id, proof=None):
        proof = proof or self._prove("consent", action_id, content_hash, rendering_hash, session_id)
        return self._gate.grant_consent(action_id, content_hash, rendering_hash, session_id, proof)

    def confirm(self, action_id, content_hash, rendering_hash, session_id, proof=None):
        proof = proof or self._prove("confirm", action_id, content_hash, rendering_hash, session_id)
        return self._gate.confirm(action_id, content_hash, rendering_hash, session_id, proof)
