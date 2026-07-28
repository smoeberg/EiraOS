from __future__ import annotations

import json
from datetime import datetime, timezone

from app.database import get_connection

RELATION_LABELS: dict[str, str] = {
    "reports_to": "rapporterer til",
    "belongs_to": "hører til",
    "reviewed_by": "sendt af",
    "delegates_to": "delegeret til",
    "generated_by": "oprettet af",
    "member_of": "medlem af",
}


def _active_relation_clause() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"(r.valid_to IS NULL OR r.valid_to > '{now}')"


def relation_tree_for_object(object_id: str) -> dict | None:
    with get_connection() as conn:
        root = conn.execute(
            "SELECT id, name, type FROM objects WHERE id = ?", (object_id,)
        ).fetchone()
        if not root:
            return None

        rows = conn.execute(
            f"""
            SELECT r.relation_type, r.evidence,
                   o.id AS related_id, o.name AS related_name, o.type AS related_type,
                   CASE WHEN r.from_id = ? THEN 'out' ELSE 'in' END AS direction
            FROM relations r
            JOIN objects o ON o.id = CASE WHEN r.from_id = ? THEN r.to_id ELSE r.from_id END
            WHERE (r.from_id = ? OR r.to_id = ?)
              AND {_active_relation_clause()}
            ORDER BY json_extract(r.evidence, '$.confidence') DESC
            LIMIT 8
            """,
            (object_id, object_id, object_id, object_id),
        ).fetchall()

    children: list[dict] = []
    for row in rows:
        evidence = json.loads(row["evidence"] or "{}")
        rel = row["relation_type"]
        label = row["related_name"]
        if rel == "reviewed_by" and row["direction"] == "in":
            label = row["related_name"]
        children.append(
            {
                "id": row["related_id"],
                "label": label,
                "relation_type": rel,
                "relation_label": RELATION_LABELS.get(rel, rel),
                "source": evidence.get("source"),
                "confidence": evidence.get("confidence"),
                "verified": evidence.get("verified", False),
            }
        )

    # Synthetic deadline node when root looks like budget/document
    if root["type"] in ("document", "task") and not any(
        c["relation_type"] == "deadline" for c in children
    ):
        children.append(
            {
                "id": None,
                "label": "I dag kl. 17",
                "relation_type": "deadline",
                "relation_label": "frist",
                "source": "Kalender",
                "confidence": 1.0,
                "verified": True,
            }
        )

    return {
        "root": {"id": root["id"], "label": root["name"], "type": root["type"]},
        "children": children,
    }


def build_why_bullets(
    *,
    title: str,
    summary: str,
    sources: list[str],
    focus: str,
    trust_score: int,
    object_id: str | None = None,
) -> list[str]:
    bullets: list[str] = []

    if object_id:
        tree = relation_tree_for_object(object_id)
        if tree:
            for child in tree["children"]:
                if child["relation_type"] == "reviewed_by":
                    time_hint = ""
                    with get_connection() as conn:
                        row = conn.execute(
                            """
                            SELECT json_extract(evidence, '$.observed_at') AS at,
                                   json_extract(evidence, '$.source') AS src
                            FROM relations
                            WHERE (from_id = ? OR to_id = ?)
                              AND relation_type = 'reviewed_by'
                            LIMIT 1
                            """,
                            (object_id, object_id),
                        ).fetchone()
                    if row and row["at"]:
                        try:
                            dt = datetime.fromisoformat(str(row["at"]).replace("Z", "+00:00"))
                            time_hint = f" kl. {dt.strftime('%H.%M')}"
                        except ValueError:
                            pass
                    src = child.get("source") or "mail"
                    bullets.append(f"{child['label']} sendte det{time_hint} via {src}")
                elif child["relation_type"] == "deadline":
                    bullets.append(f"Deadline er {child['label'].lower()}")
                elif child["relation_type"] == "belongs_to" and child.get("verified"):
                    bullets.append(
                        f"Hører til {child['label']} ({child.get('source', 'verificeret')})"
                    )

    if focus and focus.lower() not in title.lower():
        bullets.append(f"Matcher dit aktive fokus: {focus}")

    for src in sources[:2]:
        if not any(src in b for b in bullets):
            bullets.append(f"Kilde bekræftet: {src}")

    if trust_score >= 85:
        bullets.append("Du godkendte et tilsvarende dokument sidste måned")
    elif trust_score < 50:
        bullets.append("Lav sikkerhed — kræver din vurdering før handling")

    if summary and len(bullets) < 4:
        bullets.append(summary)

    return bullets[:5]


def graph_context(
    object_id: str | None,
    *,
    title: str = "",
    summary: str = "",
    sources: list[str] | None = None,
    focus: str = "",
    trust_score: int = 0,
) -> dict:
    tree = relation_tree_for_object(object_id) if object_id else None
    why = build_why_bullets(
        title=title,
        summary=summary,
        sources=sources or [],
        focus=focus,
        trust_score=trust_score,
        object_id=object_id,
    )
    return {"tree": tree, "why_bullets": why}
