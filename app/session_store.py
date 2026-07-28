from __future__ import annotations

import uuid

from app.database import get_connection, utc_now_iso

DEFAULT_ACTOR = {
    "actor_id": "mette@kommune.dk",
    "actor_name": "Mette",
    "org_unit": "Skoleforvaltningen",
    "delegated_for": "Skoleforvaltningen",
}


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
        if row:
            return sid

        actor = actor_id or DEFAULT_ACTOR["actor_id"]
        conn.execute(
            """
            INSERT INTO sessions
            (session_id, actor_id, actor_name, org_unit, assurance_level,
             delegated_for, presentation_mode, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'explorer', ?, ?)
            """,
            (
                sid,
                actor,
                actor_name or DEFAULT_ACTOR["actor_name"],
                org_unit or DEFAULT_ACTOR["org_unit"],
                assurance_level or "eid_low",
                delegated_for or org_unit or DEFAULT_ACTOR["delegated_for"],
                now,
                now,
            ),
        )
    return sid


def create_session_from_claims(claims: dict, *, session_id: str | None = None) -> str:
    """OIDC login — map id_token/userinfo claims to a new session."""
    email = str(claims.get("email") or claims.get("sub") or "").strip()
    return ensure_session(
        session_id,
        email or None,
        actor_name=str(claims.get("name") or email.split("@")[0] if email else "User"),
        org_unit=str(claims.get("org_unit") or "Kommune"),
        delegated_for=str(claims.get("org_unit") or claims.get("delegated_for") or "Kommune"),
        assurance_level=str(claims.get("assurance_level") or "idp_authenticated"),
    )


def get_session(session_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    if not row:
        return None
    return {
        "session_id": row["session_id"],
        "actor_id": row["actor_id"],
        "actor_name": row["actor_name"],
        "org_unit": row["org_unit"],
        "assurance_level": row["assurance_level"],
        "delegated_for": row["delegated_for"],
        "presentation_mode": row["presentation_mode"],
    }


def update_assurance(session_id: str, assurance_level: str) -> dict:
    now = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            "UPDATE sessions SET assurance_level = ?, updated_at = ? WHERE session_id = ?",
            (assurance_level, now, session_id),
        )
    session = get_session(session_id)
    if not session:
        raise ValueError("session not found")
    return session


def get_presentation_mode(session_id: str) -> str:
    session = get_session(session_id)
    return session["presentation_mode"] if session else "explorer"


def set_presentation_mode(session_id: str, mode: str) -> str:
    now = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            "UPDATE sessions SET presentation_mode = ?, updated_at = ? WHERE session_id = ?",
            (mode, now, session_id),
        )
    return mode
