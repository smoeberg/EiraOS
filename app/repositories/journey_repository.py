from __future__ import annotations

from app.database import get_connection, utc_now_iso
from app.models import JourneyStep, JourneySummary


class JourneyRepository:
    def list_journeys(self) -> list[JourneySummary]:
        with get_connection() as conn:
            journeys_rows = conn.execute("SELECT * FROM journeys ORDER BY created_at ASC").fetchall()
            result = []
            for j_row in journeys_rows:
                steps_rows = conn.execute(
                    "SELECT * FROM journey_steps WHERE journey_id = ? ORDER BY step_order ASC",
                    (j_row["id"],),
                ).fetchall()
                steps = [
                    JourneyStep(
                        id=s["id"],
                        step_order=s["step_order"],
                        label=s["label"],
                        actor_name=s["actor_name"],
                        status=s["status"],
                    )
                    for s in steps_rows
                ]
                pct = int((j_row["current_step"] / j_row["total_steps"]) * 100) if j_row["total_steps"] > 0 else 0
                progress_bar = f"{pct}%"
                result.append(
                    JourneySummary(
                        id=j_row["id"],
                        title=j_row["title"],
                        total_steps=j_row["total_steps"],
                        current_step=j_row["current_step"],
                        progress_bar=progress_bar,
                        steps=steps,
                    )
                )
            return result

    def get_journey(self, journey_id: str) -> JourneySummary | None:
        with get_connection() as conn:
            j_row = conn.execute("SELECT * FROM journeys WHERE id = ?", (journey_id,)).fetchone()
            if not j_row:
                return None
            steps_rows = conn.execute(
                "SELECT * FROM journey_steps WHERE journey_id = ? ORDER BY step_order ASC",
                (journey_id,),
            ).fetchall()
            steps = [
                JourneyStep(
                    id=s["id"],
                    step_order=s["step_order"],
                    label=s["label"],
                    actor_name=s["actor_name"],
                    status=s["status"],
                )
                for s in steps_rows
            ]
            pct = int((j_row["current_step"] / j_row["total_steps"]) * 100) if j_row["total_steps"] > 0 else 0
            progress_bar = f"{pct}%"
            return JourneySummary(
                id=j_row["id"],
                title=j_row["title"],
                total_steps=j_row["total_steps"],
                current_step=j_row["current_step"],
                progress_bar=progress_bar,
                steps=steps,
            )

    def advance_journey(self, journey_id: str) -> JourneySummary | None:
        journey = self.get_journey(journey_id)
        if not journey:
            return None
        if journey.current_step >= journey.total_steps:
            return journey

        next_step = journey.current_step + 1
        now = utc_now_iso()
        with get_connection() as conn:
            conn.execute(
                "UPDATE journey_steps SET status = 'completed', completed_at = ? WHERE journey_id = ? AND step_order = ?",
                (now, journey_id, next_step),
            )
            new_status = "completed" if next_step == journey.total_steps else "active"
            conn.execute(
                "UPDATE journeys SET current_step = ?, status = ?, updated_at = ? WHERE id = ?",
                (next_step, new_status, now, journey_id),
            )
        return self.get_journey(journey_id)
