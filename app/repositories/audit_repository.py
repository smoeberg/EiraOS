from __future__ import annotations

import json
from typing import Any
from app.database import get_connection, utc_now_iso
from app.models import AuditEvent


class AuditRepository:
    def list_events(self, limit: int = 20) -> list[AuditEvent]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, event_type, payload, created_at FROM audit_events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            AuditEvent(
                id=row["id"],
                event_type=row["event_type"],
                payload=json.loads(row["payload"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def create_event(self, event_id: str, event_type: str, payload: dict[str, Any]) -> AuditEvent:
        created_at = utc_now_iso()
        payload_str = json.dumps(payload)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO audit_events (id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
                (event_id, event_type, payload_str, created_at),
            )
        return AuditEvent(id=event_id, event_type=event_type, payload=payload, created_at=created_at)
