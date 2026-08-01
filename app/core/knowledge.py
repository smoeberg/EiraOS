from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class KnowledgeEntry(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    state_id: UUID
    transformation_name: str
    explanation: str
    proof_type: str = "EXPLANATION"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    valid_until_ns: Optional[int] = None
    created_at_ns: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1e9)
    )


class KnowledgeRepository:
    def __init__(self) -> None:
        self._entries: list[KnowledgeEntry] = []

    def add_entry(self, entry: KnowledgeEntry) -> None:
        self._entries.append(entry)

    def get_proofs_for_state(self, state_id: UUID) -> list[KnowledgeEntry]:
        return [entry for entry in self._entries if entry.state_id == state_id]
