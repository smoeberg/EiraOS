"""Callers for gate tests (bilag A pkt. 1). Production callers come from
SO_PEERCRED; tests set them explicitly, like the IPC layer does."""

from __future__ import annotations

from app.gate.caller import Caller

HUMAN_UID = 1000
HUMAN = Caller(uid=HUMAN_UID, pid=4242, model=False)
OTHER_HUMAN = Caller(uid=1001, pid=4343, model=False)
MODEL = Caller(uid=990, pid=4444, model=True)

# What an authenticated login leaves in the session store, for HUMAN_UID.
HUMAN_SESSION = {"authenticated_at": "2026-11-09T06:00:00Z", "os_uid": HUMAN_UID}


class Peer:
    """Stand-in for PeerCredentials as the daemon server passes it."""

    def __init__(self, caller: Caller):
        self.uid, self.pid, self.gid, self.groups = caller.uid, caller.pid, caller.uid, frozenset()
