"""Intent daemon with mandatory CEL constraint enforcement."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from app.core.event import EventBus
from app.core.knowledge import KnowledgeEntry, KnowledgeRepository
from app.core.policy_store import PolicyStore
from app.core.state import State
from app.core.transformation import ConstraintViolation, IntegratedEngine
from app.intent_parser import IntentParser
from app.ipc.jsonrpc import CONSTRAINT_VIOLATION, JsonRpcError


class StateAppender(Protocol):
    def append(self, state: State) -> None: ...


class RpcStateStore:
    """StateStore-compatible adapter that persists immutable state via stated."""

    def append(self, state: State) -> None:
        from app.ipc.client import IpcClient

        IpcClient("stated").call("state.append", state.model_dump(mode="json"))


class IntentDaemonService:
    def __init__(
        self,
        *,
        parser: IntentParser | None = None,
        policy_store: PolicyStore | None = None,
        state_store: StateAppender | None = None,
        event_bus: EventBus | None = None,
        knowledge_repository: KnowledgeRepository | None = None,
    ) -> None:
        self.parser = parser or IntentParser.from_environment()
        self.policy_store = policy_store or PolicyStore()
        self.state_store = state_store or RpcStateStore()
        self.event_bus = event_bus or EventBus()
        self.knowledge_repository = knowledge_repository or KnowledgeRepository()
        self.engine = IntegratedEngine(self.state_store, self.event_bus)  # type: ignore[arg-type]

    @staticmethod
    def _world_state(params: dict[str, Any]) -> dict[str, Any]:
        world = dict(params.get("world") or {})
        actor = dict(world.get("actor") or {})
        for key in ("actor_id", "assurance_level", "org_unit"):
            if key in params:
                actor[key] = params[key]
        actor.setdefault("id", actor.get("actor_id", "anonymous"))
        actor.setdefault("assurance_level", "eid_low")
        world["actor"] = actor
        world.setdefault("now", datetime.now(timezone.utc).isoformat())
        return world

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        raw_input = params.get("intent") or params.get("raw_input")
        if not isinstance(raw_input, str) or not raw_input.strip():
            raise JsonRpcError(-32602, "intent or raw_input is required")

        world = self._world_state(params)
        proposal = self.parser.parse(
            raw_input,
            context=params.get("context")
            if isinstance(params.get("context"), dict)
            else None,
        )
        if proposal.suggested_transformation == "clarify_intent":
            raise JsonRpcError(
                -32002,
                "CLARIFICATION_REQUIRED",
                {
                    "rationale": proposal.rationale,
                    "confidence": proposal.confidence_score,
                },
            )

        constraints = self.policy_store.get_constraints(
            proposal.suggested_transformation
        )
        try:
            state = self.engine.apply_proposal(proposal, constraints, world)
        except ConstraintViolation as exc:
            constraint = exc.constraint
            data: dict[str, Any] = {
                "rule_id": constraint.id,
                "rule": constraint.expression,
                "transformation": proposal.suggested_transformation,
                "user_message": constraint.error_message,
            }
            required_assurance = constraint.metadata.get("required_assurance")
            if required_assurance:
                data.update(
                    {
                        "step_up_required": True,
                        "required_assurance": required_assurance,
                        "step_up_method": constraint.metadata.get(
                            "step_up_method", "mitid_erhverv"
                        ),
                    }
                )
            raise JsonRpcError(
                CONSTRAINT_VIOLATION,
                "CONSTRAINT_VIOLATION",
                data,
            ) from exc

        knowledge = KnowledgeEntry(
            state_id=state.id,
            transformation_name=proposal.suggested_transformation,
            explanation=proposal.rationale,
            proof_type="CEL_CONSTRAINT",
            confidence=proposal.confidence_score,
        )
        self.knowledge_repository.add_entry(knowledge)
        return {
            "status": "executed",
            "proposal_id": str(proposal.proposal_id),
            "transformation": proposal.suggested_transformation,
            "state": state.model_dump(mode="json"),
            "confidence_score": proposal.confidence_score,
            "rationale": proposal.rationale,
            "applied_constraints": [
                {"id": item.id, "version": item.version, "expression": item.expression}
                for item in constraints
            ],
            "knowledge_entry": knowledge.model_dump(mode="json"),
        }


_DEFAULT_SERVICE: IntentDaemonService | None = None


def default_service() -> IntentDaemonService:
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = IntentDaemonService()
    return _DEFAULT_SERVICE


def intent_execute(params: dict[str, Any]) -> dict[str, Any]:
    return default_service().execute(params)


def register_intent_handlers(
    server, service: IntentDaemonService | None = None
) -> IntentDaemonService:
    try:
        from app.daemons.intent_engine import (
            register_intent_handlers as register_legacy,
        )

        register_legacy(server)
    except ImportError:
        pass
    active = service or default_service()
    server.register("intent.execute", active.execute)
    server.register("health", lambda _: {"daemon": "eira-intentd", "ok": True})
    return active
