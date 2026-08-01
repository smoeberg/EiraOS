from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class State(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1)
    timestamp_ns: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1e9)
    )
    type: str
    payload: Dict[str, Any]
    previous_state_id: Optional[UUID] = None
    hash: str = Field(default="")

    def model_post_init(self, __context: Any) -> None:
        if not self.hash:
            object.__setattr__(self, "hash", self.compute_hash())

    def compute_hash(self) -> str:
        data = {
            "id": str(self.id),
            "version": self.version,
            "timestamp_ns": self.timestamp_ns,
            "type": self.type,
            "payload": self.payload,
            "previous_state_id": (
                str(self.previous_state_id) if self.previous_state_id else None
            ),
        }
        return hashlib.sha3_256(
            json.dumps(data, sort_keys=True).encode("utf-8")
        ).hexdigest()


class ProposalState(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposal_id: UUID = Field(default_factory=uuid4)
    suggested_transformation: str
    candidate_state: State
    confidence_score: float = Field(ge=0.0, le=1.0)
    source_model: str
    rationale: str
