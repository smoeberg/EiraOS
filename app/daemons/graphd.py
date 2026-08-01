from __future__ import annotations

import json

from app.graph_context import graph_context as build_graph_context
from app.ipc.jsonrpc import JsonRpcError
from app.temporal import relations_between


def graph_temporal_query(params: dict) -> dict:
    from_name = params.get("from_name")
    to_name = params.get("to_name")
    as_of = params.get("as_of")
    if not all([from_name, to_name, as_of]):
        raise JsonRpcError(-32602, "from_name, to_name, as_of required")

    relations = relations_between(from_name, to_name, as_of)
    return {
        "query": f"Hvem var {from_name} i forhold til {to_name} ved {as_of}?",
        "relations": [relation.model_dump(mode="json") for relation in relations],
    }


def graph_context_query(params: dict) -> dict:
    object_id = params.get("object_id")
    return build_graph_context(
        object_id,
        title=params.get("title", ""),
        summary=params.get("summary", ""),
        sources=params.get("sources") or [],
        focus=params.get("focus", ""),
        trust_score=int(params.get("trust_score", 0)),
    )


def graph_provenance_trace(params: dict) -> dict:
    """Trace a claim through generic temporal graph objects and relations."""
    from app.database import get_connection

    claim_id = params.get("id") or params.get("claim_id")
    claim_text = params.get("text")
    if not claim_id and not claim_text:
        return {"origin": None, "relations": [], "source_reliability": None}

    with get_connection() as connection:
        if claim_id:
            claim = connection.execute(
                "SELECT id, name, metadata FROM objects WHERE id = ? AND type = 'claim'",
                (str(claim_id),),
            ).fetchone()
        else:
            claim = connection.execute(
                "SELECT id, name, metadata FROM objects WHERE name = ? AND type = 'claim' LIMIT 1",
                (str(claim_text),),
            ).fetchone()
        if not claim:
            return {"origin": None, "relations": [], "source_reliability": None}

        rows = connection.execute(
            """
            SELECT r.relation_type, r.valid_from, r.valid_to, r.evidence,
                   related.id AS related_id, related.name AS related_name,
                   related.type AS related_type
            FROM relations AS r
            JOIN objects AS related
              ON related.id = CASE WHEN r.from_id = ? THEN r.to_id ELSE r.from_id END
            WHERE r.from_id = ? OR r.to_id = ?
            ORDER BY r.valid_from ASC
            """,
            (claim["id"], claim["id"], claim["id"]),
        ).fetchall()

    relation_links: list[dict] = []
    reliabilities: list[float] = []
    origin = None
    for row in rows:
        evidence = json.loads(row["evidence"] or "{}")
        confidence = max(0.0, min(1.0, float(evidence.get("confidence", 0.5))))
        reliabilities.append(confidence)
        relation_type = row["relation_type"]
        stance = {
            "contradicts": "contradicts",
            "refutes": "contradicts",
            "supports": "supports",
            "corroborates": "supports",
            "derived_from": "derived_from",
            "generated_by": "derived_from",
        }.get(relation_type, relation_type)
        link = {
            "relation_type": relation_type,
            "stance": stance,
            "confidence": confidence,
            "related_id": row["related_id"],
            "related_name": row["related_name"],
            "related_type": row["related_type"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "source": evidence.get("source"),
        }
        relation_links.append(link)
        if origin is None and stance == "derived_from":
            origin = link

    metadata = json.loads(claim["metadata"] or "{}")
    if origin is None:
        origin = metadata.get("origin")
    reliability = (
        sum(reliabilities) / len(reliabilities)
        if reliabilities
        else metadata.get("source_reliability")
    )
    return {
        "origin": origin,
        "relations": relation_links,
        "source_reliability": reliability,
    }


def register_graph_handlers(server) -> None:
    server.register("graph.temporal_query", graph_temporal_query)
    server.register("graph.context", graph_context_query)
    server.register("graph.provenance.trace", graph_provenance_trace)
    server.register("health", lambda _: {"daemon": "eira-object-graphd", "ok": True})
