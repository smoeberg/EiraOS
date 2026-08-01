from __future__ import annotations

from typing import Any, Dict, List
from pydantic import BaseModel
from app.core.state import State


class Constraint(BaseModel):
    id: str
    expression: str
    error_message: str

    def evaluate(self, candidate_state: State, world_state: Dict[str, Any]) -> bool:
        ctx = {
            "candidate": candidate_state.model_dump(mode="json"),
            "world": world_state,
            "payload": candidate_state.payload
        }
        try:
            return bool(eval(self.expression, {"__builtins__": None}, ctx))
        except Exception:
            return False
