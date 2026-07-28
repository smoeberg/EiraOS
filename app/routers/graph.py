from fastapi import APIRouter
from app.models import GraphContextResponse, TemporalQueryRequest
from app.routers.common import graph_ipc, ipc_http

router = APIRouter(prefix="/v1/graph", tags=["Knowledge Graph"])

@router.get("/context", response_model=GraphContextResponse)
def graph_context_endpoint(
    object_id: str | None = None,
    title: str = "",
    summary: str = "",
    focus: str = "Kommunepilot",
    trust_score: int = 0,
    sources: str = "",
):
    try:
        source_list = [s.strip() for s in sources.split(",") if s.strip()] if sources else []
        result = graph_ipc.call(
            "graph.context",
            {
                "object_id": object_id,
                "title": title,
                "summary": summary,
                "sources": source_list,
                "focus": focus,
                "trust_score": trust_score,
            },
        )
        return GraphContextResponse.model_validate(result)
    except Exception as exc:
        raise ipc_http(exc) from exc

@router.post("/temporal")
def temporal_query(body: TemporalQueryRequest):
    try:
        return graph_ipc.call(
            "graph.temporal_query",
            body.model_dump(),
        )
    except Exception as exc:
        raise ipc_http(exc) from exc
