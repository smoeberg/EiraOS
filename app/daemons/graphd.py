from __future__ import annotations

import json

from app.ipc.jsonrpc import JsonRpcError


def graph_temporal_query(params: dict) -> dict:
    from app.temporal import relations_between

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
    from app.graph_context import graph_context as build_graph_context

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


def graph_spatial_snapshot(params: dict) -> dict:
    """Project stated's immutable chain into stable canvas coordinates."""
    from app.ipc.client import IpcClient

    limit = max(1, min(int(params.get("limit", 500)), 10_000))
    result = IpcClient("stated").call("state.list", {"limit": limit})
    states = list(result.get("states", []))
    by_id = {str(state["id"]): state for state in states}
    depth_cache: dict[str, int] = {}

    def depth(state_id: str, visiting: set[str] | None = None) -> int:
        if state_id in depth_cache:
            return depth_cache[state_id]
        chain = set(visiting or ())
        if state_id in chain:
            return 0
        chain.add(state_id)
        state = by_id[state_id]
        previous = state.get("previous_state_id")
        value = 0 if not previous or str(previous) not in by_id else depth(str(previous), chain) + 1
        depth_cache[state_id] = value
        return value

    rows: dict[int, int] = {}
    nodes = []
    edges = []
    for state in states:
        state_id = str(state["id"])
        column = depth(state_id)
        row = rows.get(column, 0)
        rows[column] = row + 1
        payload = state.get("payload") or {}
        label = payload.get("title") or payload.get("name") or state.get("type")
        node = {
            "id": state_id,
            "label": str(label),
            "type": str(state.get("type", "State")),
            "x": 100 + column * 300,
            "y": 90 + row * 170,
            "state": state,
        }
        trust_score = payload.get("trust_score")
        if isinstance(trust_score, (int, float)):
            node["trust_score"] = max(0, min(100, float(trust_score)))
        nodes.append(node)

        previous = state.get("previous_state_id")
        if previous and str(previous) in by_id:
            edges.append(
                {
                    "id": f"{previous}:{state_id}",
                    "source": str(previous),
                    "target": state_id,
                    "relation": "proposes"
                    if state.get("type") == "ProposalState"
                    else "previous",
                }
            )
    return {"nodes": nodes, "edges": edges, "count": len(nodes)}


def register_graph_handlers(server) -> None:
    server.register("graph.temporal_query", graph_temporal_query)
    server.register("graph.context", graph_context_query)
    server.register("graph.provenance.trace", graph_provenance_trace)
    server.register("graph.spatial_snapshot", graph_spatial_snapshot)
    server.register("health", lambda _: {"daemon": "eira-object-graphd", "ok": True})
