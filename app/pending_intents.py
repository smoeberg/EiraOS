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


def get_pending(intent_id: str, session_id: str | None = None) -> dict | None:
    with get_connection() as conn:
        if session_id:
            row = conn.execute(
                """
                SELECT payload FROM pending_intents
                WHERE intent_id = ? AND session_id = ?
                """,
                (intent_id, session_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT payload FROM pending_intents WHERE intent_id = ?",
                (intent_id,),
            ).fetchone()
    if not row:
        return None
    return json.loads(row["payload"])


def delete_pending(intent_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM pending_intents WHERE intent_id = ?", (intent_id,))



def claim_pending(intent_id: str, session_id: str) -> bool:
    """Atomically claim a pending intent for one execution attempt.

    The row is retained as an idempotency record; a second confirmation cannot
    claim an intent that is already executing or has completed.
    """
    now = utc_now_iso()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE pending_intents
            SET status = 'executing', updated_at = ?
            WHERE intent_id = ? AND session_id = ?
              AND status = 'pending_confirmation'
            """,
            (now, intent_id, session_id),
        )
        return cursor.rowcount == 1


def mark_execution_failed(intent_id: str) -> None:
    """Record a failed attempt without making it automatically retryable."""
    now = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE pending_intents SET status = 'execution_failed', updated_at = ?
            WHERE intent_id = ? AND status = 'executing'
            """,
            (now, intent_id),
        )


def mark_executed(intent_id: str) -> None:
    now = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE pending_intents SET status = 'executed', updated_at = ?
            WHERE intent_id = ?
            """,
            (now, intent_id),
        )
