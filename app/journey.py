from __future__ import annotations

from app.database import get_connection
from app.models import JourneyDetail, JourneyStep, JourneySummary


def _progress_bar(current: int, total: int) -> str:
    filled = round((current / total) * 8) if total else 0
    return "█" * filled + "░" * (8 - filled)


def _load_steps(journey_id: str) -> list[JourneyStep]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM journey_steps
            WHERE journey_id = ?
            ORDER BY step_order ASC
            """,
            (journey_id,),
        ).fetchall()
    return [
        JourneyStep(
            id=row["id"],
            step_order=row["step_order"],
            label=row["label"],
            actor_name=row["actor_name"],
            status=row["status"],
        )
        for row in rows
    ]


def list_journeys() -> list[JourneySummary]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM journeys WHERE status = 'active' ORDER BY created_at DESC"
        ).fetchall()

    result = []
    for row in rows:
        steps = _load_steps(row["id"])
        result.append(
            JourneySummary(
                id=row["id"],
                title=row["title"],
                total_steps=row["total_steps"],
                current_step=row["current_step"],
                progress_bar=_progress_bar(row["current_step"], row["total_steps"]),
                steps=steps,
            )
        )
    return result


def get_journey(journey_id: str) -> JourneyDetail | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM journeys WHERE id = ?", (journey_id,)
        ).fetchone()
    if not row:
        return None
    steps = _load_steps(journey_id)
    return JourneyDetail(
        id=row["id"],
        title=row["title"],
        total_steps=row["total_steps"],
        current_step=row["current_step"],
        progress_bar=_progress_bar(row["current_step"], row["total_steps"]),
        steps=steps,
        status=row["status"],
    )
