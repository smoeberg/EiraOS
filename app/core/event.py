from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Event(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp_ns: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1e9)
    )
    topic: str
    payload: dict[str, Any]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[Event], None]]] = {}
        self._audit_log: list[Event] = []

    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        self._subscribers.setdefault(topic, []).append(handler)

    def publish(self, event: Event) -> None:
        self._audit_log.append(event)
        for handler in self._subscribers.get(event.topic, []):
            handler(event)

    def get_audit_log(self) -> list[Event]:
        return list(self._audit_log)
