"""Trust items for the dashboard (read-only), formerly in app/intent_parser.py."""

from __future__ import annotations

import json

from app.database import get_connection
from app.models import TrustItem, score_to_trust_level


def list_trust_items() -> list[TrustItem]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM trust_items ORDER BY sort_order ASC").fetchall()
    return [
        TrustItem(
            id=row["id"],
            title=row["title"],
            summary=row["summary"],
            trust_score=row["trust_score"],
            trust_level=score_to_trust_level(row["trust_score"]),
            sources=json.loads(row["sources"]),
            object_id=row["object_id"],
        )
        for row in rows
    ]
