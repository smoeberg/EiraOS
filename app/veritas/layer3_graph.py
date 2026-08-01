"""Temporal provenance scoring against the EiraOS knowledge graph."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol


class TemporalGraphProvider(Protocol):
    def trace_claim(self, claim: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class Layer3Result:
    score: float
    flags: tuple[str, ...]
    relation_links: tuple[Mapping[str, Any], ...]
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["flags"] = list(self.flags)
        result["relation_links"] = [dict(item) for item in self.relation_links]
        return result


class NullTemporalGraphProvider:
    def trace_claim(self, claim: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"origin": None, "relations": [], "source_reliability": None}


class GraphdTemporalProvider:
    """Production adapter for the graph.provenance.trace JSON-RPC method."""

    def __init__(self, timeout: float = 2.0) -> None:
        self.timeout = timeout

    def trace_claim(self, claim: Mapping[str, Any]) -> Mapping[str, Any]:
        from app.ipc.client import IpcClient

        result = IpcClient("graphd", timeout=self.timeout).call(
            "graph.provenance.trace", dict(claim)
        )
        if not isinstance(result, Mapping):
            raise TypeError("graphd provenance response must be an object")
        return result


class CallableGraphProvider:
    """Adapter for graphd RPC functions or test doubles."""

    def __init__(self, query: Callable[[Mapping[str, Any]], Mapping[str, Any]]) -> None:
        self.query = query

    def trace_claim(self, claim: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.query(claim)


class Layer3GraphEngine:
    def __init__(self, provider: TemporalGraphProvider | None = None) -> None:
        self.provider = provider or GraphdTemporalProvider()

    def evaluate(self, claim: Mapping[str, Any] | str | None) -> dict[str, Any]:
        if claim is None:
            claim_data: dict[str, Any] = {}
        elif isinstance(claim, str):
            claim_data = {"text": claim}
        else:
            claim_data = dict(claim)

        try:
            trace = dict(self.provider.trace_claim(claim_data))
        except Exception as exc:  # noqa: BLE001 - graphd boundary must degrade safely
            return Layer3Result(
                score=0.35,
                flags=("graph_unavailable",),
                relation_links=(),
                details={"error": type(exc).__name__},
            ).to_dict()

        raw_relations = trace.get("relations") or trace.get("relation_links") or []
        relations: Sequence[Mapping[str, Any]] = [
            item for item in raw_relations if isinstance(item, Mapping)
        ]
        flags: list[str] = []

        score = 0.50
        origin = trace.get("origin")
        if origin:
            score += 0.12
        else:
            flags.append("origin_unresolved")

        reliability_raw = trace.get("source_reliability")
        if reliability_raw is None:
            reliability = 0.5
            flags.append("historical_reliability_unknown")
        else:
            reliability = max(0.0, min(1.0, float(reliability_raw)))
        score += (reliability - 0.5) * 0.30

        supporting_weight = 0.0
        contradicting_weight = 0.0
        contradiction_count = 0
        for relation in relations:
            stance = str(
                relation.get("stance") or relation.get("relation_type") or ""
            ).casefold()
            confidence = max(0.0, min(1.0, float(relation.get("confidence", 0.5))))
            if stance in {
                "contradicts",
                "contradiction",
                "refutes",
                "temporal_contradiction",
            }:
                contradiction_count += 1
                contradicting_weight += confidence
            elif stance in {"supports", "corroborates", "confirms", "derived_from"}:
                supporting_weight += confidence

        if contradiction_count:
            flags.append("temporal_contradiction")
            score -= min(0.55, 0.20 * contradicting_weight)
        if supporting_weight:
            score += min(0.22, 0.08 * supporting_weight)
        if not relations:
            flags.append("no_graph_relations")

        score = round(max(0.0, min(1.0, score)), 4)
        return Layer3Result(
            score=score,
            flags=tuple(dict.fromkeys(flags)),
            relation_links=tuple(dict(item) for item in relations),
            details={
                "origin": origin,
                "source_reliability": reliability,
                "supporting_weight": round(supporting_weight, 4),
                "contradicting_weight": round(contradicting_weight, 4),
                "contradiction_count": contradiction_count,
            },
        ).to_dict()

    analyze = evaluate
