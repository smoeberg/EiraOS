from __future__ import annotations

from app.models import JourneySummary
from app.repositories.journey_repository import JourneyRepository


class JourneyService:
    def __init__(self, repo: JourneyRepository | None = None) -> None:
        self.repo = repo or JourneyRepository()

    def get_all_journeys(self) -> list[JourneySummary]:
        return self.repo.list_journeys()

    def get_journey_by_id(self, journey_id: str) -> JourneySummary | None:
        return self.repo.get_journey(journey_id)

    def advance_journey_step(self, journey_id: str) -> JourneySummary | None:
        return self.repo.advance_journey(journey_id)
