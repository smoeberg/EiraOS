from __future__ import annotations

import json
import uuid

from app.database import get_connection, utc_now_iso
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


def advance_journey(journey_id: str) -> JourneyDetail | None:
    journey = get_journey(journey_id)
    if not journey or journey.status != "active":
        return journey

    next_pending = next(
        (s for s in journey.steps if s.status == "pending"), None
    )
    if not next_pending:
        return journey

    now = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE journey_steps
            SET status = 'completed', completed_at = ?
            WHERE id = ?
            """,
            (now, next_pending.id),
        )
        new_step = journey.current_step + 1
        status = "completed" if new_step >= journey.total_steps else "active"
        conn.execute(
            """
            UPDATE journeys
            SET current_step = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_step, status, now, journey_id),
        )
        conn.execute(
            """
            INSERT INTO audit_events (id, event_type, payload, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                "journey.step_completed",
                json.dumps(
                    {
                        "journey_id": journey_id,
                        "step_id": next_pending.id,
                        "step_label": next_pending.label,
                    }
                ),
                now,
            ),
        )

    return get_journey(journey_id)
