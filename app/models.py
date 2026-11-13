from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TrustLevel(str, Enum):
    UNCONFIRMED = "unconfirmed"
    INDICATIVE = "indicative"
    PROBABLE = "probable"
    CONFIRMED = "confirmed"
    INDISPUTABLE = "indisputable"


def score_to_trust_level(score: int) -> TrustLevel:
    if score <= 20:
        return TrustLevel.UNCONFIRMED
    if score <= 50:
        return TrustLevel.INDICATIVE
    if score <= 79:
        return TrustLevel.PROBABLE
    if score <= 95:
        return TrustLevel.CONFIRMED
    return TrustLevel.INDISPUTABLE


class TrustItem(BaseModel):
    id: str
    title: str
    summary: str
    trust_score: int = Field(ge=0, le=100)
    trust_level: TrustLevel
    sources: list[str] = []
    object_id: str | None = None


class JourneyStep(BaseModel):
    id: str
    step_order: int
    label: str
    actor_name: str | None
    status: str


class JourneySummary(BaseModel):
    id: str
    title: str
    total_steps: int
    current_step: int
    progress_bar: str
    steps: list[JourneyStep]


class JourneyDetail(JourneySummary):
    status: str


class DashboardResponse(BaseModel):
    greeting: str
    focus: str
    state: str
    session_id: str | None = None
    actor_id: str | None = None
    trust_items: list[TrustItem]
    active_journeys: list[JourneySummary]
    presentation_mode: str = "explorer"


class CapabilityEntry(BaseModel):
    action: str
    resource: str
    assurance: str | None = None


class CapabilityManifest(BaseModel):
    adapter_id: str
    name: str
    version: str
    conformance: str = "CORE"
    capabilities: list[CapabilityEntry]


class TemporalQueryRequest(BaseModel):
    from_name: str
    to_name: str
    as_of: str


class RelationEvidence(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
    source: str
    verified: bool
    observed_at: str
    method: str
    adapter_id: str | None = None
    assurance_level: str | None = None


class TemporalRelation(BaseModel):
    relation_type: str
    from_name: str
    to_name: str
    valid_from: str
    valid_to: str | None
    evidence: RelationEvidence | None = None


class GraphContextResponse(BaseModel):
    tree: dict | None = None
    why_bullets: list[str] = []


class AuditEvent(BaseModel):
    id: str
    event_type: str
    payload: dict
    created_at: str

