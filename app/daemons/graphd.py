from __future__ import annotations

from app.ipc.jsonrpc import JsonRpcError
from app.temporal import relations_between
from app.graph_context import graph_context as build_graph_context


def graph_temporal_query(params: dict) -> dict:
    from_name = params.get("from_name")
    to_name = params.get("to_name")
    as_of = params.get("as_of")
    if not all([from_name, to_name, as_of]):
        raise JsonRpcError(-32602, "from_name, to_name, as_of required")

    relations = relations_between(from_name, to_name, as_of)
    return {
        "query": f"Hvem var {from_name} i forhold til {to_name} ved {as_of}?",
        "relations": [r.model_dump(mode="json") for r in relations],
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


def register_graph_handlers(server) -> None:
    server.register("graph.temporal_query", graph_temporal_query)
    server.register("graph.context", graph_context_query)
    server.register("health", lambda _: {"daemon": "eira-object-graphd", "ok": True})
