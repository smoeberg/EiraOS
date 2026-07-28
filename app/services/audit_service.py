from __future__ import annotations

from typing import Any
from app.models import AuditEvent
from app.repositories.audit_repository import AuditRepository


class AuditService:
    def __init__(self, repo: AuditRepository | None = None) -> None:
        self.repo = repo or AuditRepository()

    def get_recent_events(self, limit: int = 20) -> list[AuditEvent]:
        return self.repo.list_events(limit=limit)

    def log_event(self, event_id: str, event_type: str, payload: dict[str, Any]) -> AuditEvent:
        return self.repo.create_event(event_id=event_id, event_type=event_type, payload=payload)
