from __future__ import annotations

from typing import Any, Dict, List, Optional
from app.core.state import State, ProposalState
from app.core.constraint import Constraint
from app.core.store import StateStore
from app.core.event import Event, EventBus


class IntegratedEngine:
    def __init__(self, store: StateStore, event_bus: EventBus):
        self.store = store
        self.event_bus = event_bus

    def apply_proposal(
        self,
        proposal: ProposalState,
        constraints: List[Constraint],
        world_state: Dict[str, Any]
    ) -> State:
        for c in constraints:
            if not c.evaluate(proposal.candidate_state, world_state):
                raise ValueError(f"Constraint violation: {c.error_message}")

        self.store.append(proposal.candidate_state)
        self.event_bus.publish(Event(
            topic="state.transformed",
            payload={"state_id": str(proposal.candidate_state.id), "type": proposal.candidate_state.type}
        ))
        return proposal.candidate_state
