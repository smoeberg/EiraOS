from __future__ import annotations

import json
from datetime import datetime

from app.database import get_connection
from app.models import RelationEvidence, TemporalRelation


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def relations_between(
    from_name: str, to_name: str, as_of: str
) -> list[TemporalRelation]:
    as_of_dt = _parse_iso(as_of)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT r.relation_type, r.valid_from, r.valid_to, r.evidence,
                   o_from.name AS from_name, o_to.name AS to_name
            FROM relations r
            JOIN objects o_from ON o_from.id = r.from_id
            JOIN objects o_to ON o_to.id = r.to_id
            WHERE o_from.name = ? AND o_to.name = ?
            ORDER BY r.valid_from ASC
            """,
            (from_name, to_name),
        ).fetchall()

    result: list[TemporalRelation] = []
    for row in rows:
        valid_from = _parse_iso(row["valid_from"])
        valid_to = _parse_iso(row["valid_to"]) if row["valid_to"] else None
        if valid_from <= as_of_dt and (valid_to is None or valid_to > as_of_dt):
            evidence_raw = row["evidence"] if "evidence" in row.keys() else "{}"
            evidence_data = json.loads(evidence_raw or "{}")
            evidence = (
                RelationEvidence(**evidence_data)
                if evidence_data.get("source")
                else None
            )
            result.append(
                TemporalRelation(
                    relation_type=row["relation_type"],
                    from_name=row["from_name"],
                    to_name=row["to_name"],
                    valid_from=row["valid_from"],
                    valid_to=row["valid_to"],
                    evidence=evidence,
                )
            )
    return result
