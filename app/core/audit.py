"""Tamper-evident audit events stored as immutable EiraOS states."""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Protocol
from uuid import uuid4

from app.core.state import State


class AuditStateStore(Protocol):
    def append(self, state: State) -> None: ...

    def list_states(self) -> list[State]: ...


@dataclass(frozen=True)
class AuditVerification:
    valid: bool
    events: int
    head_hash: str | None
    errors: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["errors"] = list(self.errors)
        return result


class StateAuditTrail:
    """Append and verify a dedicated hash chain inside the immutable state log."""

    state_type = "AuditEvent"

    def __init__(self, store: AuditStateStore) -> None:
        self.store = store
        self._lock = threading.RLock()

    def _events(self) -> list[State]:
        events = [state for state in self.store.list_states() if state.type == self.state_type]
        return sorted(
            events,
            key=lambda state: (int(state.payload.get("sequence", 0)), state.timestamp_ns),
        )

    def append(
        self,
        event_type: str,
        details: dict[str, Any],
        *,
        actor_id: str = "system",
        timestamp_ns: int | None = None,
    ) -> State:
        if not event_type.strip() or len(event_type) > 200:
            raise ValueError("audit event_type must contain 1-200 characters")
        if not isinstance(details, dict):
            raise TypeError("audit details must be an object")
        with self._lock:
            events = self._events()
            previous = events[-1] if events else None
            occurred_at_ns = timestamp_ns or time.time_ns()
            state = State(
                id=uuid4(),
                version=1,
                timestamp_ns=occurred_at_ns,
                type=self.state_type,
                previous_state_id=previous.id if previous else None,
                payload={
                    "event_id": str(uuid4()),
                    "sequence": len(events) + 1,
                    "event_type": event_type,
                    "actor_id": actor_id,
                    "occurred_at_ns": occurred_at_ns,
                    "details": details,
                    "previous_audit_hash": previous.hash if previous else None,
                },
            )
            self.store.append(state)
            return state

    def verify(
        self,
        *,
        expected_head_hash: str | None = None,
        expected_events: int | None = None,
    ) -> AuditVerification:
        errors: list[str] = []
        events = self._events()
        previous: State | None = None
        for sequence, state in enumerate(events, start=1):
            if not state.is_hash_valid():
                errors.append(f"event_{sequence}:state_hash_invalid")
            if state.payload.get("sequence") != sequence:
                errors.append(f"event_{sequence}:sequence_invalid")
            expected_id = previous.id if previous else None
            if state.previous_state_id != expected_id:
                errors.append(f"event_{sequence}:previous_state_invalid")
            expected_hash = previous.hash if previous else None
            if state.payload.get("previous_audit_hash") != expected_hash:
                errors.append(f"event_{sequence}:previous_hash_invalid")
            previous = state
        if expected_events is not None and len(events) != expected_events:
            errors.append("external_event_count_mismatch")
        actual_head = events[-1].hash if events else None
        if expected_head_hash is not None and actual_head != expected_head_hash:
            errors.append("external_head_hash_mismatch")
        return AuditVerification(
            valid=not errors,
            events=len(events),
            head_hash=actual_head,
            errors=tuple(errors),
        )
