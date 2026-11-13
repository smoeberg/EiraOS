import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from app import consent_keys


def new_consent_key() -> str:
    from app.gate.consent_proof import new_key

    return new_key()


# An authenticated desktop session counts for at most a working day; then the
# user logs in again. A leaked session id is worth nothing after that.
SESSION_LIFETIME = timedelta(hours=12)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_db_path() -> str:
    # EIRA_APP_DB is what the installed units set (/data/eira-app.db, allowed
    # by AppArmor); the relative default is only for a development checkout.
    path = os.environ.get("EIRA_DB_PATH") or os.environ.get("EIRA_APP_DB") or "data/eira.db"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return path

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn

def init_db(conn: sqlite3.Connection | None = None) -> None:
    close = False
    if conn is None:
        conn = sqlite3.connect(get_db_path())
        close = True
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            event_type TEXT,
            payload TEXT,
            details TEXT,
            actor_id TEXT,
            created_at TEXT,
            timestamp TEXT
        );

        -- Presentation mode belongs to the OS user at the desk, proven by
        -- SO_PEERCRED, not to a session a client names (UDVIKLINGSPLAN F1.5).
        CREATE TABLE IF NOT EXISTS presentation_modes (
            os_uid INTEGER PRIMARY KEY,
            mode TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            actor_id TEXT,
            actor_name TEXT,
            org_unit TEXT,
            assurance_level TEXT,
            delegated_for TEXT,
            presentation_mode TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """)
        # Bilag A pkt. 1: a session counts for the gate only if it was
        # authenticated from verified claims, and only for the OS user that
        # logged in. Sessions made by naming an actor id have neither.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        for column, kind in (
            ("os_uid", "INTEGER"),
            ("authenticated_at", "TEXT"),
            # From verified claims only: the gate's identity and groups, and
            # when the session stops counting.
            ("identity", "TEXT"),
            ("groups_json", "TEXT"),
            ("expires_at", "TEXT"),
            # Kept only so old databases open; never written. Consent keys
            # live in RAM (app/consent_keys.py).
            ("consent_key", "TEXT"),
            # The logind session the login came from: the agent claims the key
            # of its own logind session, never one the app names.
            ("logind_session", "TEXT"),
        ):
            if column not in columns:
                conn.execute(f"ALTER TABLE sessions ADD COLUMN {column} {kind}")
        # Upgrade: erase consent keys earlier versions wrote to disk, with
        # freed pages zeroed (EIRA-CONSENT-AGENT §5.3).
        if conn.execute(
            "SELECT 1 FROM sessions WHERE consent_key IS NOT NULL LIMIT 1"
        ).fetchone():
            conn.execute("PRAGMA secure_delete=ON")
            conn.execute("UPDATE sessions SET consent_key = NULL")
        conn.commit()
    finally:
        if close:
            conn.close()

def ensure_session(
    session_id: str | None,
    actor_id: str | None = None,
    *,
    actor_name: str | None = None,
    org_unit: str | None = None,
    delegated_for: str | None = None,
    assurance_level: str | None = None,
) -> str:
    sid = session_id or str(uuid.uuid4())
    now = utc_now_iso()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT session_id FROM sessions WHERE session_id = ?", (sid,)
        ).fetchone()

        if not row:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, actor_id, actor_name, org_unit,
                    assurance_level, delegated_for, presentation_mode,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    actor_id or "anonymous",
                    actor_name or "Anonymous",
                    org_unit or "Default",
                    assurance_level or "eid_low",
                    delegated_for or "Self",
                    "normal",
                    now,
                    now,
                ),
            )
            conn.commit()
    return sid

def create_session_from_claims(
    claims: dict, *, session_id: str | None = None, os_uid: int | None = None,
    logind_session: str | None = None,
) -> str:
    """The only way to a session the gate accepts: claims the caller has
    verified, bound to the OS user who logged in (`os_uid`). Without
    `os_uid` the session is not bound, and the gate refuses it.

    Session fixation: a login always creates its own row in one statement.
    A requested id is used only if that INSERT succeeds; an id that exists —
    or that someone inserts concurrently — is never adopted (no
    check-then-act between transactions).
    """
    actor_id = claims.get("email") or claims.get("sub") or "user"
    actor_name = claims.get("name") or actor_id
    org_unit = claims.get("org_unit") or "Default"
    now = utc_now_iso()
    identity = claims.get("identity")
    groups_json = json.dumps(sorted(claims.get("groups") or []))
    expires = (datetime.now(timezone.utc) + SESSION_LIFETIME).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidates = ([session_id] if session_id else []) + [str(uuid.uuid4())]
    with get_connection() as conn:
        for sid in candidates:
            cursor = conn.execute(
                """
                INSERT INTO sessions (
                    session_id, actor_id, actor_name, org_unit, assurance_level,
                    delegated_for, presentation_mode, created_at, updated_at,
                    os_uid, authenticated_at, identity, groups_json, expires_at, logind_session
                ) VALUES (?, ?, ?, ?, 'idp_authenticated', 'Self', 'normal', ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO NOTHING
                """,
                (sid, actor_id, actor_name, org_unit, now, now, os_uid, now, identity, groups_json, expires,
                 logind_session),
            )
            if cursor.rowcount == 1:
                # The key is made in RAM, never in this database. If it cannot
                # be stored, the login fails rather than leave a session that
                # would need a key on disk.
                consent_keys.put(sid, new_consent_key())
                conn.commit()
                return sid
    raise RuntimeError("could not create a fresh session")


# Never leaves the session store except to the gate: identity.session and
# dashboard.get hand sessions to whoever names the id.
SECRET_FIELDS = ("consent_key",)


def _read_session(session_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row:
            return None
        session = dict(row)
        raw_groups = session.pop("groups_json", None)
        session["groups"] = json.loads(raw_groups) if raw_groups else []
        return session


def get_session(session_id: str) -> dict | None:
    """A session as clients may see it: without its secrets."""
    session = _read_session(session_id)
    if session is not None:
        for field in SECRET_FIELDS:
            session.pop(field, None)
    return session


def get_session_for_gate(session_id: str) -> dict | None:
    """The gate's view, including the consent key it verifies proofs with.
    Only the gate kernel may use this. The key comes from RAM and only for
    this boot; after a reboot it is None, and every proof fails."""
    session = _read_session(session_id)
    if session is not None:
        session["consent_key"] = consent_keys.get(session_id)
    return session

def update_assurance(session_id: str, assurance_level: str) -> dict:
    ensure_session(session_id)
    now = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            "UPDATE sessions SET assurance_level = ?, updated_at = ? WHERE session_id = ?",
            (assurance_level, now, session_id),
        )
        conn.commit()
    session = get_session(session_id)
    if session is None:
        raise RuntimeError("Session not found after update")
    return session

def mode_for_uid(os_uid: int) -> str:
    """The presentation mode of an OS user; Explorer until set (ADR-0001)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT mode FROM presentation_modes WHERE os_uid = ?", (os_uid,)
        ).fetchone()
    return row["mode"] if row else "explorer"


def set_mode_for_uid(os_uid: int, mode: str) -> str:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO presentation_modes (os_uid, mode, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(os_uid) DO UPDATE SET mode = excluded.mode,
                                                 updated_at = excluded.updated_at""",
            (os_uid, mode, utc_now_iso()),
        )
        conn.commit()
    return mode


def session_of_caller(os_uid: int, session_id: str | None = None) -> dict | None:
    """The caller's own authenticated, unexpired session, without secrets.

    With ``session_id``: that session, only if it belongs to ``os_uid``.
    Without: the caller's newest one. Never creates a session, and never
    returns another user's (fundregister S-5)."""
    # The same format expires_at is written in, so text comparison is time order.
    # Fail closed: a session without expires_at (pre-upgrade row) is no session.
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        if session_id:
            row = conn.execute(
                """SELECT session_id FROM sessions WHERE session_id = ? AND os_uid = ?
                   AND authenticated_at IS NOT NULL
                   AND expires_at IS NOT NULL AND expires_at > ?""",
                (session_id, os_uid, now),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT session_id FROM sessions WHERE os_uid = ?
                   AND authenticated_at IS NOT NULL
                   AND expires_at IS NOT NULL AND expires_at > ?
                   ORDER BY authenticated_at DESC LIMIT 1""",
                (os_uid, now),
            ).fetchone()
    return get_session(row["session_id"]) if row else None


