import os
import sqlite3
import uuid
from datetime import datetime, timezone

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_db_path() -> str:
    path = os.environ.get("EIRA_DB_PATH", "data/eira.db")
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
        conn.execute("""
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

def create_session_from_claims(claims: dict, *, session_id: str | None = None) -> str:
    actor_id = claims.get("email") or claims.get("sub") or "user"
    actor_name = claims.get("name") or actor_id
    org_unit = claims.get("org_unit") or "Default"
    return ensure_session(
        session_id,
        actor_id,
        actor_name=actor_name,
        org_unit=org_unit,
        assurance_level="idp_authenticated",
    )

def get_session(session_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row:
            return None
        return dict(row)

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

def get_presentation_mode(session_id: str) -> str:
    session = get_session(session_id)
    if not session:
        return "normal"
    return session.get("presentation_mode", "normal")

def set_presentation_mode(session_id: str, mode: str) -> str:
    ensure_session(session_id)
    now = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            "UPDATE sessions SET presentation_mode = ?, updated_at = ? WHERE session_id = ?",
            (mode, now, session_id),
        )
        conn.commit()
    return mode
