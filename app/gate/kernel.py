"""Gate Kernel 1.0: den eneste vej til en beskyttet handling.

To trin, begge gennem alle lag i fast rækkefølge:

``propose(raw, session, origin)``
    Lag 1–4 validerer forslaget, og det gemmes som ``pending`` (bundet til
    sit indholdshash). Derefter afgør lag 5–6, hvad der mangler: samtykke
    (``E_NEED_CONSENT``), step-up (``E_STEP_UP_REQUIRED``) eller rettighed
    (``E_UNAUTHORIZED``). Intet udføres.

``confirm(action_id, content_hash, session)``
    *Hele* handlingen valideres igen fra lag 1 ud fra den gemte rå input.
    Bekræftelsen skal være bundet til samme hash (lag 7), handlingen claimes
    atomart, autorisationen tjekkes igen lige før udførelse, og først da
    kaldes executoren (lag 8) med en engangsbillet.

En PASS logges først, når executoren har returneret et verificeret resultat.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Callable

from app.gate import edp
from app.gate.errors import GATE_VERSION, Decision, GateCode, GateResult, LayerFailure
from app.gate.executors import ExecutorRegistry, default_registry
from app.gate.policy import (
    POLICY_VERSION,
    ActionPolicy,
    Origin,
    assurance_rank,
    check_limits,
    policy_for,
)
from app.gate.store import GateStore, iso, utc_now

FINISHED_STATES = {"executed", "partial", "failed", "unknown"}
DEFAULT_CONSENT_TTL = timedelta(minutes=10)


class Gate:
    def __init__(
        self,
        store: GateStore | None = None,
        registry: ExecutorRegistry | None = None,
        *,
        sessions: Callable[[str], dict[str, Any] | None] | None = None,
        clock: Callable[[], datetime] = utc_now,
        consent_ttl: timedelta = DEFAULT_CONSENT_TTL,
    ) -> None:
        self.store = store or GateStore()
        self._registry = registry if registry is not None else default_registry(self.store.db_path)
        if sessions is None:
            from app.session_store import get_session

            sessions = get_session
        self._sessions = sessions
        self._clock = clock
        self._consent_ttl = consent_ttl

    # --- public API ----------------------------------------------------------

    def propose(self, raw: str | bytes | None, session_id: str | None, origin: Origin) -> GateResult:
        actor = self._actor(session_id)
        try:
            envelope, policy = self._layers_1_to_4(raw, origin, actor)
            digest = edp.content_hash(envelope)
            record = self._store_pending(raw, envelope, digest, policy, origin, session_id, actor)
            if record["state"] != "pending":
                return self._existing(record)
            self._layer_5_consent(policy, record, session_id, at_proposal=True)
            self._layer_6_authorization(envelope, policy, actor)
        except LayerFailure as failure:
            if failure.code is GateCode.E_UNAUTHORIZED and failure.layer == 6:
                # Only reached after this user's own pending record was stored.
                self.store.cancel(envelope["id"])
            return self._fail("propose", raw, failure, actor)
        result = GateResult(
            decision=None,
            action_id=envelope["id"],
            state="pending",
            content_hash=digest,
            detail="ready for confirmation",
            data={"reversibility": policy.reversibility.value},
        )
        self._audit("propose", result, raw, actor)
        return result

    def propose_from_model(
        self, produce: Callable[[], str | bytes | None], session_id: str | None
    ) -> GateResult:
        """Runs the model and gates its output. An unavailable or crashing
        runtime is a safe REJECT, never a fallback."""
        try:
            raw = produce()
        except Exception:  # noqa: BLE001 - any runtime failure is a rejection
            raw = None
        return self.propose(raw, session_id, Origin.MODEL)

    def grant_consent(self, action_id: str, content_hash: str, session_id: str | None) -> GateResult:
        """The user's explicit consent to exactly this action and parameters."""
        actor = self._actor(session_id)
        record = self.store.find(action_id)
        try:
            if record is None or record["state"] != "pending":
                raise LayerFailure(GateCode.E_STATE, "no pending action to consent to")
            if actor is None or actor["identity"] != record["actor_identity"]:
                raise LayerFailure(GateCode.E_UNAUTHORIZED, "only the proposing user can consent")
            if content_hash != record["content_hash"]:
                raise LayerFailure(GateCode.E_CONSENT, "consent does not cover these parameters")
        except LayerFailure as failure:
            return self._fail("consent", None, failure, actor, action_id=action_id)
        consent_id = self.store.grant_consent(
            action_id, content_hash, session_id or "", self._clock() + self._consent_ttl
        )
        result = GateResult(
            decision=None,
            action_id=action_id,
            state="pending",
            content_hash=content_hash,
            detail="consent recorded",
            data={"consent_id": consent_id},
        )
        self._audit("consent", result, None, actor)
        return result

    def confirm(self, action_id: str, content_hash: str, session_id: str | None) -> GateResult:
        actor = self._actor(session_id)
        record = self.store.find(action_id)
        if record is None:
            return self._fail(
                "confirm", None, LayerFailure(GateCode.E_STATE, "unknown action"), actor, action_id=action_id
            )
        raw = record["raw"]
        try:
            # Full re-validation from the stored input: no earlier PASS is reused.
            envelope, policy = self._layers_1_to_4(raw, Origin(record["origin"]), actor)
            if policy.fingerprint() != record["policy_fingerprint"]:
                raise LayerFailure(GateCode.E_POLICY, "gate policy changed since the proposal")
            self._layer_5_consent(policy, record, session_id, at_proposal=False)
            self._layer_6_authorization(envelope, policy, actor)
            execution_id = self._layer_7_state(record, envelope, content_hash)
            if isinstance(execution_id, GateResult):
                return execution_id
        except LayerFailure as failure:
            return self._fail("confirm", raw, failure, actor)
        return self._layer_8_execute(envelope, record, content_hash, execution_id, actor)

    def status(self, action_id: str) -> dict[str, Any] | None:
        record = self.store.find(action_id)
        if record is None:
            return None
        return {
            "action_id": record["action_id"],
            "conversation_id": record["conversation_id"],
            "action_type": record["action_type"],
            "state": record["state"],
            "content_hash": record["content_hash"],
            "execution_id": record["execution_id"],
            "result": json.loads(record["result"]) if record["result"] else None,
        }

    # --- layers --------------------------------------------------------------

    def _layers_1_to_4(
        self, raw: str | bytes | None, origin: Origin, actor: dict[str, Any] | None
    ) -> tuple[dict[str, Any], ActionPolicy]:
        envelope = edp.layer1_syntax(raw)
        edp.layer2_schema(envelope)
        edp.layer3_semantics(envelope, self.store)
        # Layer 4 — security policy. Degraded transport changes nothing here.
        policy = policy_for(envelope["action"]["type"])
        if origin not in policy.allowed_origins:
            raise LayerFailure(
                GateCode.E_POLICY, f"{policy.action_type} may not be proposed by {origin.value}"
            )
        check_limits(policy, envelope["action"]["content"])
        if actor is None or not self.store.is_member(envelope["conversation_id"], actor["identity"]):
            raise LayerFailure(GateCode.E_POLICY, "conversation is outside the user's domain")
        return envelope, policy

    def _layer_5_consent(
        self, policy: ActionPolicy, record: dict[str, Any], session_id: str | None, *, at_proposal: bool
    ) -> None:
        if not policy.requires_consent:
            return
        now = self._clock()
        consents = self.store.consents_for(record["action_id"])
        for consent in consents:
            if (
                consent["content_hash"] == record["content_hash"]
                and consent["session_id"] == session_id
                and consent["revoked_at"] is None
                and datetime.fromisoformat(consent["expires_at"]) > now
            ):
                return
        if at_proposal and not consents:
            raise LayerFailure(
                GateCode.E_NEED_CONSENT,
                "irreversible action: the user must consent to exactly this",
                data={"reversibility": policy.reversibility.value},
            )
        raise LayerFailure(GateCode.E_CONSENT, "no valid consent covers this action")

    def _layer_6_authorization(
        self, envelope: dict[str, Any], policy: ActionPolicy, actor: dict[str, Any] | None
    ) -> None:
        if actor is None:
            raise LayerFailure(GateCode.E_UNAUTHORIZED, "no authenticated session")
        identity = actor["identity"]
        acting = [p for p in envelope["participants"] if p["identity"] == identity and p["role"] == "member"]
        if not acting:
            raise LayerFailure(GateCode.E_UNAUTHORIZED, "the user is not an acting participant")
        if not self.store.has_right(identity, envelope["conversation_id"], policy.action_type, self._clock()):
            raise LayerFailure(GateCode.E_UNAUTHORIZED, f"no right to {policy.action_type} here")
        if assurance_rank(actor["assurance_level"]) < assurance_rank(policy.required_assurance):
            raise LayerFailure(
                GateCode.E_STEP_UP_REQUIRED,
                f"requires {policy.required_assurance}",
                data={"required_assurance": policy.required_assurance},
            )

    def _layer_7_state(
        self, record: dict[str, Any], envelope: dict[str, Any], content_hash: str
    ) -> str | GateResult:
        if record["state"] in FINISHED_STATES:
            return self._existing(record)  # idempotency: never execute twice
        if record["state"] != "pending":
            raise LayerFailure(GateCode.E_STATE, f"action is {record['state']}")
        if content_hash != record["content_hash"] or edp.content_hash(envelope) != record["content_hash"]:
            raise LayerFailure(GateCode.E_STATE, "confirmation is not bound to these parameters")
        execution_id = self.store.claim(record["action_id"], content_hash)
        if execution_id is None:
            latest = self.store.find(record["action_id"])
            if latest and latest["state"] in FINISHED_STATES:
                return self._existing(latest)
            raise LayerFailure(GateCode.E_STATE, "action is being executed by another request")
        return execution_id

    def _layer_8_execute(
        self,
        envelope: dict[str, Any],
        record: dict[str, Any],
        content_hash: str,
        execution_id: str,
        actor: dict[str, Any] | None,
    ) -> GateResult:
        action_id = record["action_id"]
        action_type = envelope["action"]["type"]
        # Authorization again, immediately before the side effect (§3.6).
        try:
            current = self._actor(record["session_id"])
            self._layer_6_authorization(envelope, policy_for(action_type), current)
        except LayerFailure as failure:
            self.store.release(action_id, execution_id)
            return self._fail("confirm", record["raw"], failure, actor)
        if not self._registry.has(action_type):
            self.store.release(action_id, execution_id)
            return self._fail(
                "confirm",
                record["raw"],
                LayerFailure(GateCode.E_EXECUTOR_UNAVAILABLE, f"no executor for {action_type}"),
                actor,
            )
        ticket = self._registry.issue(action_id, content_hash, execution_id)
        executor = self._registry.executor(action_type)
        try:
            outcome = self._registry.call(ticket, envelope, content_hash)
        except Exception as error:  # noqa: BLE001 - outcome is unknown, never "success"
            self.store.finish(action_id, execution_id, "unknown", {"error": type(error).__name__})
            return self._partial(record, execution_id, "unknown", "executor failed; outcome unknown", actor)
        if outcome.status != "succeeded":
            state = outcome.status if outcome.status in {"partial", "failed"} else "unknown"
            self.store.finish(action_id, execution_id, state, outcome.result)
            return self._partial(record, execution_id, state, f"executor reported {outcome.status}", actor)
        if outcome.state_transition not in executor.success_transitions:
            self.store.finish(action_id, execution_id, "unknown", outcome.result)
            return self._partial(
                record, execution_id, "unknown", "executor reported an invalid transition", actor
            )
        self.store.finish(action_id, execution_id, "executed", outcome.result)
        result = GateResult(
            decision=Decision.PASS,
            action_id=action_id,
            layer=8,
            state="executed",
            content_hash=content_hash,
            execution_id=execution_id,
            result=outcome.result,
        )
        self._audit("confirm", result, record["raw"], actor)  # PASS only after the result
        return result

    # --- helpers -------------------------------------------------------------

    def _actor(self, session_id: str | None) -> dict[str, Any] | None:
        """The authenticated user behind a session. Sessions are never created
        here: an unknown session id is no session."""
        if not session_id:
            return None
        session = self._sessions(session_id)
        if not session:
            return None
        identity = self.store.identity_for(session["actor_id"])
        if identity is None:
            return None
        return {
            "session_id": session_id,
            "identity": identity,
            "assurance_level": session.get("assurance_level"),
        }

    def _store_pending(
        self,
        raw: str | bytes | None,
        envelope: dict[str, Any],
        digest: str,
        policy: ActionPolicy,
        origin: Origin,
        session_id: str | None,
        actor: dict[str, Any] | None,
    ) -> dict[str, Any]:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        inserted = self.store.insert_pending(
            {
                "action_id": envelope["id"],
                "conversation_id": envelope["conversation_id"],
                "action_type": envelope["action"]["type"],
                "origin": origin.value,
                "session_id": session_id or "",
                "actor_identity": actor["identity"] if actor else "",
                "raw": text,
                "content_hash": digest,
                "policy_version": POLICY_VERSION,
                "policy_fingerprint": policy.fingerprint(),
            }
        )
        record = self.store.find(envelope["id"])
        assert record is not None
        if not inserted and (
            record["content_hash"] != digest
            or record["actor_identity"] != (actor["identity"] if actor else "")
        ):
            raise LayerFailure(GateCode.E_STATE, "action id already used with other parameters")
        return record

    def _existing(self, record: dict[str, Any]) -> GateResult:
        result = json.loads(record["result"]) if record["result"] else None
        state = record["state"]
        if state == "executed":
            return GateResult(
                decision=Decision.PASS,
                action_id=record["action_id"],
                layer=8,
                state=state,
                content_hash=record["content_hash"],
                execution_id=record["execution_id"],
                result=result,
                detail="already executed (idempotent)",
            )
        if state in {"partial", "failed", "unknown"}:
            return GateResult(
                decision=Decision.REJECT,
                action_id=record["action_id"],
                layer=8,
                code=GateCode.E_PARTIAL,
                state=state,
                content_hash=record["content_hash"],
                execution_id=record["execution_id"],
                result=result,
                detail="earlier execution did not succeed; not retried automatically",
            )
        return GateResult(
            decision=None,
            action_id=record["action_id"],
            state=state,
            content_hash=record["content_hash"],
        )

    def _partial(
        self, record: dict[str, Any], execution_id: str, state: str, detail: str, actor: dict[str, Any] | None
    ) -> GateResult:
        result = GateResult(
            decision=Decision.REJECT,
            action_id=record["action_id"],
            layer=8,
            code=GateCode.E_PARTIAL,
            state=state,
            content_hash=record["content_hash"],
            execution_id=execution_id,
            detail=detail,
        )
        self._audit("confirm", result, record["raw"], actor)
        return result

    def _fail(
        self,
        step: str,
        raw: str | bytes | None,
        failure: LayerFailure,
        actor: dict[str, Any] | None,
        *,
        action_id: str | None = None,
    ) -> GateResult:
        found_id = action_id or _safe_id(raw)
        record = self.store.find(found_id) if found_id else None
        result = GateResult(
            decision=failure.decision,
            action_id=found_id,
            layer=failure.layer,
            code=failure.code,
            detail=failure.detail,
            state=record["state"] if record else None,
            content_hash=record["content_hash"] if record else None,
            data=failure.data,
        )
        self._audit(step, result, raw, actor)
        return result

    def _audit(
        self, step: str, result: GateResult, raw: str | bytes | None, actor: dict[str, Any] | None
    ) -> None:
        self.store.append_audit(
            {
                "gate": GATE_VERSION,
                "step": step,
                "action_id": result.action_id,
                "decision": result.decision.value if result.decision else None,
                "layer": result.layer,
                "error": result.code.value if result.code else None,
                "state": result.state,
                "participant": actor["identity"] if actor else None,
                "timestamp": iso(self._clock()),
                "input_hash": edp.input_hash(raw) if raw is not None else None,
                "policy_version": POLICY_VERSION,
            }
        )


def _safe_id(raw: str | bytes | None) -> str | None:
    """Best-effort action id for audit; never trusted for anything else."""
    try:
        data = json.loads(raw) if raw is not None else None
    except (ValueError, TypeError):
        return None
    value = data.get("id") if isinstance(data, dict) else None
    return value if isinstance(value, str) and 0 < len(value) <= 200 else None
