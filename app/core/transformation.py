from __future__ import annotations

from typing import Any

from app.core.constraint import Constraint
from app.core.event import Event, EventBus
from app.core.state import ProposalState, State
from app.core.store import StateStore


class ConstraintViolation(ValueError):
    def __init__(self, constraint: Constraint) -> None:
        self.constraint = constraint
        super().__init__(f"Constraint violation: {constraint.error_message}")


class IntegratedEngine:
    def __init__(self, store: StateStore, event_bus: EventBus) -> None:
        self.store = store
        self.event_bus = event_bus

    def apply_proposal(
        self,
        proposal: ProposalState,
        constraints: list[Constraint],
        world_state: dict[str, Any],
    ) -> State:
        for constraint in constraints:
            if not constraint.evaluate(proposal.candidate_state, world_state):
                raise ConstraintViolation(constraint)

        self.store.append(proposal.candidate_state)
        self.event_bus.publish(
            Event(
                topic="state.transformed",
                payload={
                    "state_id": str(proposal.candidate_state.id),
                    "type": proposal.candidate_state.type,
                    "transformation": proposal.suggested_transformation,
                },
            )
        )
        return proposal.candidate_state
