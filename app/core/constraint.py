from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.cel_evaluator import CELEvaluator
from app.core.state import State


class Constraint(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    expression: str
    error_message: str
    transformation_type: str = "*"
    version: int = Field(default=1, ge=1)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    def evaluate(
        self,
        candidate_state: State,
        world_state: dict[str, Any],
        evaluator: CELEvaluator | None = None,
    ) -> bool:
        if not self.enabled:
            return True
        candidate = candidate_state.model_dump(mode="json")
        return (evaluator or CELEvaluator()).evaluate(
            self.expression,
            candidate=candidate,
            world=world_state,
        )
