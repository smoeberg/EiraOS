from __future__ import annotations

import json
import uuid

from app.database import get_connection, init_db, utc_now_iso


def _evidence(
    confidence: float,
    source: str,
    verified: bool,
    method: str,
    adapter_id: str | None = None,
    assurance_level: str | None = None,
    observed_at: str | None = None,
) -> str:
    return json.dumps(
        {
            "confidence": confidence,
            "source": source,
            "verified": verified,
            "observed_at": observed_at or utc_now_iso(),
            "method": method,
            "adapter_id": adapter_id,
            "assurance_level": assurance_level,
        }
    )


def seed_if_empty() -> None:
    init_db()
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM objects").fetchone()["c"]
        if count > 0:
            return

    mette_id = str(uuid.uuid4())
    lars_id = str(uuid.uuid4())
    budget_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    journey_id = str(uuid.uuid4())
    now = utc_now_iso()

    objects = [
        (mette_id, "person", "Mette", None, now, now),
        (lars_id, "person", "Lars", None, now, now),
        (budget_id, "document", "Budget 2026", mette_id, now, now),
        (project_id, "project", "Kommunepilot", None, now, now),
        (org_id, "organisation", "Økonomikontoret", None, now, now),
    ]

    relations = [
        (
            str(uuid.uuid4()),
            lars_id,
            mette_id,
            "reports_to",
            "2023-01-01T00:00:00Z",
            "2024-06-30T23:59:59Z",
            _evidence(0.97, "Entra ID", True, "hr_authoritative", assurance_level="session"),
        ),
        (
            str(uuid.uuid4()),
            budget_id,
            project_id,
            "belongs_to",
            "2026-01-01T00:00:00Z",
            None,
            _evidence(0.94, "Public360", True, "adapter_sync", adapter_id="eira-adapter-public360"),
        ),
        (
            str(uuid.uuid4()),
            budget_id,
            org_id,
            "belongs_to",
            "2026-01-01T00:00:00Z",
            None,
            _evidence(0.91, "Public360", True, "adapter_sync", adapter_id="eira-adapter-public360"),
        ),
        (
            str(uuid.uuid4()),
            budget_id,
            lars_id,
            "reviewed_by",
            "2026-07-04T08:14:00Z",
            None,
            _evidence(0.93, "Exchange", True, "adapter_sync", adapter_id="eira-adapter-m365"),
        ),
    ]

    trust_items = [
        (
            str(uuid.uuid4()),
            "Budget 2026 afventer godkendelse",
            "Det samlede budget for Kommunepilot-projektet er klar til din endelige godkendelse.",
            91,
            "confirmed",
            json.dumps(["Public360", "Økonomikontoret"]),
            budget_id,
            1,
            now,
        ),
        (
            str(uuid.uuid4()),
            "Leverandør forventes at levere fredag",
            "Baseret på ordrebekræftelse og tidligere leverancer",
            71,
            "probable",
            json.dumps(["ERP-adapter", "ordre #4421"]),
            None,
            2,
            now,
        ),
        (
            str(uuid.uuid4()),
            "Tre forskellige adresser fundet",
            "AI fandt modstridende adresser i sagens dokumenter",
            18,
            "unconfirmed",
            json.dumps(["AI-udtræk"]),
            None,
            3,
            now,
        ),
    ]

    journey_steps = [
        (str(uuid.uuid4()), journey_id, 1, "Controller", "Anna", "completed"),
        (str(uuid.uuid4()), journey_id, 2, "Leder", "Peter", "completed"),
        (str(uuid.uuid4()), journey_id, 3, "Økonomichef", "Mette", "pending"),
        (str(uuid.uuid4()), journey_id, 4, "Direktion", "Direktion", "pending"),
        (str(uuid.uuid4()), journey_id, 5, "Arkivering", "System", "pending"),
    ]

    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO objects (id, type, name, owner_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            objects,
        )
        conn.executemany(
            """
            INSERT INTO relations (id, from_id, to_id, relation_type, valid_from, valid_to, evidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            relations,
        )
        conn.executemany(
            """
            INSERT INTO trust_items
            (id, title, summary, trust_score, trust_level, sources, object_id, sort_order, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            trust_items,
        )
        conn.execute(
            """
            INSERT INTO journeys (id, title, total_steps, current_step, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (journey_id, "Budget 2026", 5, 2, "active", now, now),
        )
        conn.executemany(
            """
            INSERT INTO journey_steps (id, journey_id, step_order, label, actor_name, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            journey_steps,
        )
