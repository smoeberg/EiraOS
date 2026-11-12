"""identityd's side of the consent agent (EIRA-CONSENT-AGENT §5.2–§5.3).

The app no longer holds the consent key on an installed system. A registered
agent claims it. Registration proves two things:

1. The peer runs the agent's code: its effective GID is ``eira-consent``
   (``consent_path``), which only the setgid binary gives.
2. The agent shows its windows on *this session's* compositor, not on a
   nested one that a program running as the user controls and can click in.

For (2) the agent reports the PID of the compositor at the other end of its
Wayland socket (it read that with SO_PEERCRED; the agent is trusted code,
so the report is honest about which socket it uses). identityd then checks,
from /proc, that the compositor runs as the user, in the same logind
session, and sits directly under the session's leader: at most one process
(the display manager's session launcher) between them. Everything the user
starts runs below the compositor, so a nested compositor is always deeper.
Start times are stored so a reused PID does not count.

Which Eira session the key belongs to is not something the app says: at
login identityd records the logind session the app ran in, and the agent
gets the key of the newest valid Eira session for its own uid and logind
session.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import consent_keys
from app.ipc.jsonrpc import JsonRpcError

PROC = Path(os.environ.get("EIRA_PROC", "/proc"))
LOGIND_SESSIONS = Path(os.environ.get("EIRA_LOGIND_SESSIONS", "/run/systemd/sessions"))
E_CONSENT_AGENT = -32061
# Leader -> (launcher, e.g. gdm-wayland-session) -> compositor.
MAX_DEPTH = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS consent_agents (
    agent_pid INTEGER NOT NULL,
    agent_start INTEGER NOT NULL,
    uid INTEGER NOT NULL,
    logind_session TEXT NOT NULL,
    compositor_pid INTEGER NOT NULL,
    compositor_start INTEGER NOT NULL,
    registered_at TEXT NOT NULL,
    PRIMARY KEY (agent_pid, agent_start)
);
"""


class Refused(Exception):
    pass


# --- /proc ------------------------------------------------------------------------


def _stat(pid: int) -> tuple[int, int]:
    """(ppid, start time in clock ticks) from /proc/<pid>/stat. The command
    name may contain spaces and parentheses: parse after the last ')'."""
    try:
        raw = (PROC / str(pid) / "stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        raise Refused(f"process {pid} is gone or unreadable") from None
    fields = raw[raw.rindex(")") + 2:].split()
    return int(fields[1]), int(fields[19])


def _uid(pid: int) -> int:
    try:
        for line in (PROC / str(pid) / "status").read_text(encoding="utf-8").splitlines():
            if line.startswith("Uid:"):
                return int(line.split()[1])  # real uid
    except OSError:
        pass
    raise Refused(f"cannot read the uid of {pid}")


def _read_int(pid: int, name: str) -> int:
    try:
        return int((PROC / str(pid) / name).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        raise Refused(f"cannot read {name} of {pid}") from None


def logind_session(pid: int) -> str:
    """The logind session id of a process (/proc/<pid>/sessionid)."""
    value = _read_int(pid, "sessionid")
    if value in (-1, 4294967295):
        raise Refused(f"process {pid} is in no logind session")
    return str(value)


def _leader(session: str) -> int:
    try:
        for line in (LOGIND_SESSIONS / session).read_text(encoding="utf-8").splitlines():
            if line.startswith("LEADER="):
                return int(line.split("=", 1)[1])
    except (OSError, ValueError):
        pass
    raise Refused(f"logind session {session} has no leader")


def _depth_below(pid: int, ancestor: int, limit: int) -> int | None:
    current = pid
    for depth in range(1, limit + 1):
        current, _ = _stat(current)
        if current == ancestor:
            return depth
        if current <= 1:
            return None
    return None


# --- registration and the key -------------------------------------------------------


def _connect(db_path: str | None) -> sqlite3.Connection:
    from app import database

    conn = sqlite3.connect(db_path or database.DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def register(peer, compositor_pid: Any, db_path: str | None = None) -> dict[str, Any]:
    """§5.2. ``peer`` is the SO_PEERCRED of the agent's connection."""
    from app.gate.consent_path import is_consent_agent

    if not is_consent_agent(peer.gid):
        raise Refused("only the consent agent can register (effective gid)")
    if not isinstance(compositor_pid, int) or isinstance(compositor_pid, bool) or compositor_pid <= 1:
        raise Refused("compositor_pid must be a process id")
    if peer.uid < 1000 or _read_int(peer.pid, "loginuid") != peer.uid:
        raise Refused("the agent must run as the logged-in user")
    session = logind_session(peer.pid)
    if _uid(compositor_pid) != peer.uid:
        raise Refused("the compositor does not run as this user")
    if logind_session(compositor_pid) != session:
        raise Refused("the compositor is in another logind session")
    leader = _leader(session)
    if _depth_below(compositor_pid, leader, MAX_DEPTH) is None:
        raise Refused("not the session's compositor (nested or started by the user)")
    _, agent_start = _stat(peer.pid)
    _, compositor_start = _stat(compositor_pid)
    with _connect(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO consent_agents (agent_pid, agent_start, uid, logind_session,
               compositor_pid, compositor_start, registered_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (peer.pid, agent_start, peer.uid, session, compositor_pid, compositor_start,
             datetime.now(timezone.utc).isoformat()),
        )
    return {"status": "registered", "logind_session": session}


def _registered(conn: sqlite3.Connection, peer) -> sqlite3.Row:
    """The peer's registration, still valid: same process (start time), same
    compositor still alive with its start time."""
    try:
        _, start = _stat(peer.pid)
    except Refused:
        raise Refused("agent process unreadable") from None
    row = conn.execute(
        "SELECT * FROM consent_agents WHERE agent_pid = ? AND agent_start = ? AND uid = ?",
        (peer.pid, start, peer.uid),
    ).fetchone()
    if row is None:
        raise Refused("this agent is not registered")
    try:
        _, compositor_start = _stat(row["compositor_pid"])
    except Refused:
        compositor_start = None
    if compositor_start != row["compositor_start"]:
        conn.execute("DELETE FROM consent_agents WHERE agent_pid = ? AND agent_start = ?", (peer.pid, start))
        conn.commit()  # the raise below would roll it back
        raise Refused("the compositor this agent registered with is gone")
    return row


def claim_key(peer, db_path: str | None = None) -> dict[str, Any]:
    """§5.3: the key of the newest valid Eira session of this uid in this
    logind session, to a registered agent only."""
    from app.gate.consent_path import is_consent_agent

    if not is_consent_agent(peer.gid):
        raise Refused("only the consent agent can claim the key")
    with _connect(db_path) as conn:
        registration = _registered(conn, peer)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = conn.execute(
            """SELECT session_id, identity, expires_at FROM sessions
                WHERE os_uid = ? AND logind_session = ? AND authenticated_at IS NOT NULL
                  AND expires_at > ?
                ORDER BY authenticated_at DESC""",
            (peer.uid, registration["logind_session"], now),
        ).fetchall()
    # The key lives in RAM only and only for this boot (app/consent_keys.py):
    # the newest session that still has one.
    for row in rows:
        key = consent_keys.get(row["session_id"])
        if key:
            return {**dict(row), "consent_key": key}
    raise Refused("no logged-in Eira session in this logind session")


def handlers(db_path: str | None = None):
    from app.ipc.auth import PEER_KEY

    def _peer(params: dict[str, Any]):
        peer = params.pop(PEER_KEY, None)
        if peer is None:
            raise JsonRpcError(E_CONSENT_AGENT, "E_CONSENT_AGENT", {"reason": "no caller"})
        return peer

    def register_handler(params: dict[str, Any]) -> dict[str, Any]:
        peer = _peer(params)
        try:
            return register(peer, params.get("compositor_pid"), db_path)
        except Refused as error:
            raise JsonRpcError(E_CONSENT_AGENT, "E_CONSENT_AGENT", {"reason": str(error)}) from None

    def claim_handler(params: dict[str, Any]) -> dict[str, Any]:
        peer = _peer(params)
        try:
            return claim_key(peer, db_path)
        except Refused as error:
            raise JsonRpcError(E_CONSENT_AGENT, "E_CONSENT_AGENT", {"reason": str(error)}) from None

    register_handler.wants_peer = True
    claim_handler.wants_peer = True
    return register_handler, claim_handler
