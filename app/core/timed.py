from __future__ import annotations

from uuid import UUID, uuid4
from typing import List
from pydantic import BaseModel, Field
from app.core.event import Event, EventBus


class TimedTrigger(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    trigger_at_ns: int
    target_transformation: str
    payload: dict

    def is_due(self, now_ns: int) -> bool:
        return now_ns >= self.trigger_at_ns


class TimedScheduler:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.triggers: List[TimedTrigger] = []

    def schedule(self, trigger: TimedTrigger) -> None:
        self.triggers.append(trigger)

    def tick(self, now_ns: int) -> None:
        due = [t for t in self.triggers if t.is_due(now_ns)]
        for t in due:
            self.event_bus.publish(Event(
                topic="timed.trigger_fired",
                payload={"trigger_id": str(t.id), "transformation": t.target_transformation, "payload": t.payload}
            ))
            self.triggers.remove(t)
