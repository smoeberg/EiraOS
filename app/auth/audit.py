"""Auth audit — NIS2 login trail."""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.database import get_connection, utc_now_iso


def record_auth_event(event_type: str, payload: dict[str, Any]) -> str:
    """Persist auth audit event. Never store raw tokens."""
    event_id = str(uuid.uuid4())
    safe = {k: v for k, v in payload.items() if k not in ("id_token", "access_token", "refresh_token")}
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO audit_events (id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
            (event_id, event_type, json.dumps(safe), utc_now_iso()),
        )
    return event_id
