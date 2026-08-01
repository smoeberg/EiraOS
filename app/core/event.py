from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Any, Dict, Callable, List
from pydantic import BaseModel, Field


class Event(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp_ns: int = Field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1e9))
    topic: str
    payload: Dict[str, Any]


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Event], None]]] = {}
        self._audit_log: List[Event] = []

    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)

    def publish(self, event: Event) -> None:
        self._audit_log.append(event)
        handlers = self._subscribers.get(event.topic, [])
        for handler in handlers:
            handler(event)

    def get_audit_log(self) -> List[Event]:
        return list(self._audit_log)
