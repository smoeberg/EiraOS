from __future__ import annotations

import json

from app.database import get_connection, utc_now_iso


def save_pending(session_id: str, intent_id: str, payload: dict) -> None:
    now = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO pending_intents
            (intent_id, session_id, payload, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(intent_id) DO UPDATE SET
              payload = excluded.payload,
              status = excluded.status,
              updated_at = excluded.updated_at
            """,
            (
                intent_id,
                session_id,
                json.dumps(payload),
                payload.get("status", "pending_confirmation"),
                now,
                now,
            ),
        )
