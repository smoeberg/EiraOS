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

import contextvars
import json
from datetime import datetime, timedelta
from typing import Any, Callable

from app.clock import BootInstant, boot_now, within
from app.conversation.feed import OutsideDomain
from app.gate import consent_proof, edp, system
from app.gate.caller import current as current_caller
from app.gate.errors import GATE_VERSION, Decision, GateCode, GateResult, LayerFailure
from app.gate.executors import ExecutorRegistry, ExecutorUnavailable, default_registry
from app.gate.policy import (
    POLICY_VERSION,
    ActionPolicy,
    Origin,
    assurance_rank,
    check_limits,
    policy_for,
)
from app.gate.render import LANGUAGES, RenderError, render, rendering_hash
from app.gate.store import GateStore, iso, utc_now
from app.rights import contract
from app.rights.cache import ActiveRights, RightsCache

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
        boot_clock: Callable[[], BootInstant] = boot_now,
        rights: RightsCache | None = None,
        delegations: Any = None,
    ) -> None:
        self.store = store or GateStore()
        if delegations is None:
            from app.auth.delegation import DelegationService

            delegations = DelegationService()
        # Who may let the model prepare (EIRA-DELEGATION-1.0); tests inject.
        self._delegations = delegations
        self._registry = registry if registry is not None else default_registry(self.store.db_path)
        if sessions is None:
            from app.session_store import get_session_for_gate as get_session

            sessions = get_session
        self._sessions = sessions
        self._clock = clock
        self._consent_ttl = consent_ttl
        self._boot_clock = boot_clock
        # The only source of rights (ADR-0003): the Fleet-signed set the
        # governance agent installed. No set → no rights.
        self._rights = rights if rights is not None else RightsCache()
        self.recover()

    # --- recovery --------------------------------------------------------------

    def recover(self) -> dict[str, int]:
        """Resolve actions left in ``executing`` by a crash between the claim
        and the recorded result. The executor's own durable state decides:
        found → ``executed``; provably not done → back to ``pending`` (the user
        can confirm again, nothing happens twice); cannot tell → ``unknown``.
        Never re-runs an executor."""
        counts = {"executed": 0, "pending": 0, "unknown": 0}
        for record in self.store.executing():
            action_type = record["action_type"]
            found = self._registry.reconcile(action_type, record["action_id"], record["execution_id"])
            if found is True:
                state, result = "executed", self._registry.recorded_result(action_type, record["action_id"])
                self.store.finish(record["action_id"], record["execution_id"], state, result)
            elif found is False:
                state = "pending"
                self.store.release(record["action_id"], record["execution_id"])
            else:
                state = "unknown"
                self.store.finish(record["action_id"], record["execution_id"], state, {"recovered": True})
            counts[state] += 1
            self.store.append_audit(
                {
                    "gate": GATE_VERSION,
                    "step": "recover",
                    "action_id": record["action_id"],
                    "decision": None,
                    "layer": 7,
                    "error": None,
                    "state": state,
                    "participant": record["actor_identity"] or None,
                    "timestamp": iso(self._clock()),
                    "input_hash": None,
                    "policy_version": POLICY_VERSION,
                }
            )
        return counts

    # --- public API ----------------------------------------------------------

    def propose(
        self, raw: str | bytes | None, session_id: str | None, origin: Origin, lang: str = "da"
    ) -> GateResult:
        _reset_rights()
        # The model's proposals are origin model, whatever the caller claims:
        # the IPC layer already does this, the gate does not rely on it.
        caller = current_caller()
        if caller is not None and caller.model:
            origin = Origin.MODEL
        actor = self._actor(session_id)
        record: dict[str, Any] | None = None
        try:
            envelope, policy = self._layers_1_to_4(raw, origin, actor)
            if lang not in LANGUAGES:
                raise LayerFailure(GateCode.E_POLICY, f"no rendering for language {lang!r}")
            digest = edp.content_hash(envelope)
            # What the user will see is fixed now, from the envelope alone.
            try:
                rendering = render(envelope, actor["identity"], lang)
            except RenderError as error:
                raise LayerFailure(GateCode.E_POLICY, str(error)) from None
            record = self._store_pending(raw, envelope, digest, policy, origin, session_id, actor, rendering)
            if record["state"] != "pending":
                return self._existing(record)
            self._layer_5_consent(policy, record, session_id, at_proposal=True)
            self._layer_6_authorization(envelope, policy, actor)
        except LayerFailure as failure:
            if failure.code is GateCode.E_UNAUTHORIZED and failure.layer == 6 and record is not None:
                # Layer 6 runs after the pending record is stored; use the record
                # itself for cleanup so malformed/early failures cannot reference
                # an unbound envelope.
                self.store.cancel(record["action_id"])
            elif record is not None and record["state"] == "pending":
                # Consent or step-up is needed: the UI shows exactly this text.
                failure.data.setdefault("rendering", _rendering(record))
            return self._fail("propose", raw, failure, actor)
        result = GateResult(
            decision=None,
            action_id=envelope["id"],
            state="pending",
            content_hash=digest,
            detail="ready for confirmation",
            data={"reversibility": policy.reversibility.value, "rendering": _rendering(record)},
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

    def grant_consent(
        self,
        action_id: str,
        content_hash: str,
        rendering_hash_: str,
        session_id: str | None,
        proof: str | None = None,
    ) -> GateResult:
        """The user's explicit consent to exactly this action, these parameters
        and this rendering (the text the user was shown), from the EiraOS app
        (`proof`, consent_proof.py)."""
        _reset_rights()
        if _model_is_calling():
            return self._fail("consent", None, _MODEL_CANNOT_DECIDE, None, action_id=action_id)
        actor = self._human_actor(session_id)
        bad_proof = self._proof_failure("consent", actor, action_id, content_hash, rendering_hash_, proof)
        if bad_proof is not None:
            return self._fail("consent", None, bad_proof, actor, action_id=action_id)
        record = self.store.find(action_id)
        try:
            if record is None or record["state"] != "pending":
                raise LayerFailure(GateCode.E_STATE, "no pending action to consent to")
            if actor is None or actor["identity"] != record["actor_identity"]:
                raise LayerFailure(GateCode.E_UNAUTHORIZED, "only the proposing user can consent")
            if content_hash != record["content_hash"]:
                raise LayerFailure(GateCode.E_CONSENT, "consent does not cover these parameters")
            if rendering_hash_ != record["rendering_hash"] or not _rendering_intact(record):
                raise LayerFailure(GateCode.E_CONSENT, "consent does not cover the text that was shown")
        except LayerFailure as failure:
            return self._fail("consent", None, failure, actor, action_id=action_id)
        started = self._boot_clock()
        consent_id = self.store.grant_consent(
            action_id,
            content_hash,
            rendering_hash_,
            session_id or "",
            self._clock() + self._consent_ttl,  # shown to the user, never decides
            boot_id=started.boot_id,
            boottime_ns=started.ns,
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

    def confirm(
        self,
        action_id: str,
        content_hash: str,
        rendering_hash_: str,
        session_id: str | None,
        proof: str | None = None,
    ) -> GateResult:
        _reset_rights()
        if _model_is_calling():
            return self._fail("confirm", None, _MODEL_CANNOT_DECIDE, None, action_id=action_id)
        actor = self._human_actor(session_id)
        bad_proof = self._proof_failure("confirm", actor, action_id, content_hash, rendering_hash_, proof)
        if bad_proof is not None:
            return self._fail("confirm", None, bad_proof, actor, action_id=action_id)
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
            execution_id = self._layer_7_state(record, envelope, content_hash, rendering_hash_)
            if isinstance(execution_id, GateResult):
                return execution_id
        except LayerFailure as failure:
            return self._fail("confirm", raw, failure, actor)
        return self._layer_8_execute(envelope, record, content_hash, execution_id, actor)

    def gate_state(self, action_id: str) -> str | None:
        """Internal state for tests and recovery; not exposed over IPC."""
        record = self.store.find(action_id)
        return record["state"] if record else None

    def status(self, action_id: str, session_id: str | None) -> dict[str, Any] | None:
        """Only the acting user or a member of the conversation may see an
        action; anyone else gets the same answer as for an unknown id."""
        record = self.store.find(action_id)
        if record is None:
            return None
        actor = self._actor(session_id)
        if actor is None or (
            actor["identity"] != record["actor_identity"]
            and not self.store.is_member(record["conversation_id"], actor["identity"])
        ):
            return None
        return {
            "action_id": record["action_id"],
            "conversation_id": record["conversation_id"],
            "action_type": record["action_type"],
            "state": record["state"],
            "content_hash": record["content_hash"],
            "execution_id": record["execution_id"],
            "result": json.loads(record["result"]) if record["result"] else None,
            "rendering": _rendering(record),
        }

    # --- layers --------------------------------------------------------------

    def _layers_1_to_4(
        self, raw: str | bytes | None, origin: Origin, actor: dict[str, Any] | None
    ) -> tuple[dict[str, Any], ActionPolicy]:
        """Lag 1–4 for begge handlingsfamilier (ADR-0002).

        Returns the action in the gate's common shape: an EDP envelope as is,
        or an EiraSystemAPI request as its view. Everything after this point
        is the same code for both families.
        """
        obj = edp.parse_json(raw)
        if system.is_system_request(obj):
            system.syntax(obj)
            system.schema(obj)
            action = system.view(obj, actor["identity"] if actor else "")
        else:
            action = edp.edp_syntax(obj)
            edp.layer2_schema(action)
        edp.layer3_semantics(action, self.store)
        # Layer 4 — security policy. Degraded transport changes nothing here.
        policy = policy_for(action["action"]["type"])
        if origin not in policy.allowed_origins:
            raise LayerFailure(
                GateCode.E_POLICY, f"{policy.action_type} may not be proposed by {origin.value}"
            )
        check_limits(policy, action["action"]["content"])
        self._domain(action, actor)
        # A model may propose only under a delegation from this human
        # (bilag A pkt. 1, EIRA-DELEGATION-1.0). Consent and confirmation
        # stay human-only in grant_consent() and confirm().
        caller = current_caller()
        if origin is Origin.MODEL and caller is not None and caller.model:
            self._delegation(policy, actor, caller)
        return action, policy

    def _delegation(self, policy, actor: dict[str, Any] | None, caller) -> None:
        """Lag 4 for a model proposal. The delegation used is recorded in the
        gate's own audit chain with the decision (no second audit system on
        the decision path, and nothing to fail open)."""
        from app.gate.caller import model_identity

        delegee = model_identity(caller)
        target = f"intent:{policy.action_type}"
        found = None
        if actor is not None and delegee:
            found = self._delegations.delegation_for(delegee, "prepare", target, delegator=actor["identity"])
        if found is None:
            raise LayerFailure(GateCode.E_UNAUTHORIZED, "no active delegation for this model and action")
        _DELEGATION.set({"delegation_id": found.id, "delegator": found.delegator_id,
                         "delegee": delegee, "target": target})

    def _domain(self, action: dict[str, Any], actor: dict[str, Any] | None) -> None:
        """Lag 4, the user's domain (RIGHTS-SET §6, CONVERSATION-1.0 §3.2).

        ``device:local`` is not a conversation: its domain is having at least
        one live grant on ``device:local`` in the Fleet set; which action is
        allowed is lag 6's decision. Elsewhere the conversation layer decides
        who may act.
        """
        if actor is None:
            raise LayerFailure(GateCode.E_POLICY, "outside the user's domain")
        if action["conversation_id"] == system.SYSTEM_SCOPE:
            resolved = self._rights.resolve(self._clock())
            rights = resolved.rights
            if rights is None or not contract.has_any_grant(
                rights.rights_set,
                principal=actor["identity"],
                groups=actor.get("groups") or (),
                scope=system.SYSTEM_SCOPE,
                now=rights.effective_now,
            ):
                raise LayerFailure(GateCode.E_POLICY, "outside the user's domain: no grant on this device")
            return
        try:
            self.store.check_domain(action, actor["identity"])
        except OutsideDomain as error:
            raise LayerFailure(GateCode.E_POLICY, f"outside the user's domain: {error}") from None

    def _layer_5_consent(
        self, policy: ActionPolicy, record: dict[str, Any], session_id: str | None, *, at_proposal: bool
    ) -> None:
        if not policy.requires_consent:
            return
        # Bilag A pkt. 6: validity on CLOCK_BOOTTIME within this boot. Setting
        # the wall clock back cannot extend a consent; a reboot ends it.
        now = self._boot_clock()
        ttl_ns = int(self._consent_ttl.total_seconds() * 1_000_000_000)
        consents = self.store.consents_for(record["action_id"])
        for consent in consents:
            if (
                consent["content_hash"] == record["content_hash"]
                and consent["rendering_hash"] == record["rendering_hash"]
                and consent["session_id"] == session_id
                and consent["revoked_at"] is None
                and within(_boot_instant(consent), now, ttl_ns)
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
        """EIRA-RIGHTS-SET-1.0 §6, evaluated afresh at every decision."""
        if actor is None:
            raise LayerFailure(GateCode.E_UNAUTHORIZED, "no authenticated session")
        identity = actor["identity"]
        acting = [p for p in envelope["participants"] if p["identity"] == identity and p["role"] == "member"]
        if not acting:
            raise LayerFailure(GateCode.E_UNAUTHORIZED, "the user is not an acting participant")
        resolved = self._rights.resolve(self._clock())
        rights = resolved.rights
        _RIGHTS.set(rights)
        if rights is None:
            raise LayerFailure(
                GateCode.E_UNAUTHORIZED,
                f"no rights on this device: {resolved.reason}",
                data={"rights": resolved.state, "reason": resolved.reason},
            )
        decision = contract.authorize(
            rights.rights_set,
            principal=identity,
            groups=actor.get("groups") or (),
            scope=envelope["conversation_id"],
            action=action_key(policy.action_type),
            now=rights.effective_now,
        )
        _DECISION.set(decision)
        if not decision.allowed:
            data = {"rights": "expired", "expires_at": iso(rights.expires_at)} if decision.reason == "expired" else {}
            raise LayerFailure(
                GateCode.E_UNAUTHORIZED, f"{decision.reason}: {policy.action_type} here", data=data
            )
        required = contract.stricter_assurance(policy.required_assurance, decision.required_assurance)
        if assurance_rank(actor["assurance_level"]) < assurance_rank(required):
            raise LayerFailure(
                GateCode.E_STEP_UP_REQUIRED,
                f"requires {required}",
                data={"required_assurance": required},
            )

    def rights_status(self) -> dict[str, Any]:
        """For status UI: why actions are or are not possible (§5.1)."""
        resolved = self._rights.resolve(self._clock())
        if resolved.rights is None:
            return {"state": resolved.state, "reason": resolved.reason}
        return {
            "state": resolved.state,
            "reason": resolved.reason,
            "expires_at": iso(resolved.rights.expires_at),
            **resolved.rights.audit(),
        }

    def _layer_7_state(
        self, record: dict[str, Any], envelope: dict[str, Any], content_hash: str, rendering_hash_: str
    ) -> str | GateResult:
        if record["state"] in FINISHED_STATES:
            return self._existing(record)  # idempotency: never execute twice
        if record["state"] != "pending":
            raise LayerFailure(GateCode.E_STATE, f"action is {record['state']}")
        if content_hash != record["content_hash"] or edp.content_hash(envelope) != record["content_hash"]:
            raise LayerFailure(GateCode.E_STATE, "confirmation is not bound to these parameters")
        if rendering_hash_ != record["rendering_hash"] or not _rendering_intact(record):
            raise LayerFailure(GateCode.E_STATE, "confirmation is not bound to the text that was shown")
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
        # Authorization again, immediately before the side effect (§3.6), for
        # the session that is confirming now — not the one that proposed.
        try:
            current = self._human_actor(actor["session_id"]) if actor else None
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
        except ExecutorUnavailable as error:
            # Checked before any side effect: nothing happened, so pending again.
            self.store.release(action_id, execution_id)
            return self._fail(
                "confirm",
                record["raw"],
                LayerFailure(GateCode.E_EXECUTOR_UNAVAILABLE, str(error)),
                actor,
            )
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
        """The authenticated user behind a session, for the process that is
        actually calling (bilag A pkt. 1). Sessions are never created here.

        - No caller (not over the socket) → no actor.
        - The session must have been authenticated from verified login
          claims (`authenticated_at`); a session someone created by naming
          an actor id is no session.
        - A human caller may only use a session bound to its own uid.
        - The model may name a human's session to *propose* on their behalf;
          `grant_consent` and `confirm` refuse the model outright.
        """
        caller = current_caller()
        if caller is None or not session_id:
            return None
        session = self._sessions(session_id)
        if not session or not session.get("authenticated_at"):
            return None
        expires = session.get("expires_at")
        if expires and datetime.fromisoformat(str(expires).replace("Z", "+00:00")) <= self._clock():
            return None  # an expired session is no session
        bound = session.get("os_uid")
        if bound is None:
            return None
        if caller.model:
            # The model proposes on behalf of a human session, never one bound
            # to the model itself. Which human it acts for is not yet proven:
            # that needs the UI-issued delegation of bilag A pkt. 1.
            if int(bound) == caller.uid:
                return None
        elif int(bound) != caller.uid:
            return None
        # Installed logins carry the identity from verified claims
        # (did:eira:<provider-id>.<subject>, EIRA-IDENTITY 1.0); gate_identities
        # is the binding for older sessions.
        identity = session.get("identity") or self.store.identity_for(session["actor_id"])
        if identity is None:
            return None
        return {
            "session_id": session_id,
            "identity": identity,
            "assurance_level": session.get("assurance_level"),
            # Group membership comes from identity (the provider via identityd), never
            # from the request; rights for groups come from the set (ADR-0003).
            "groups": tuple(session.get("groups") or ()),
            "caller_uid": caller.uid,
            "caller_model": caller.model,
        }

    def _proof_failure(
        self,
        verb: str,
        actor: dict[str, Any] | None,
        action_id: str,
        content_hash: str,
        rendering_hash_: str,
        proof: str | None,
    ) -> LayerFailure | None:
        """No actor is handled by the normal path (it fails there). With an
        actor, the decision must carry the app's proof for exactly this step."""
        if actor is None:
            return None
        session = self._sessions(actor["session_id"]) or {}
        if consent_proof.verify(
            session.get("consent_key"), proof, verb, actor["caller_uid"], actor["session_id"],
            action_id, content_hash, rendering_hash_,
        ):
            return None
        return LayerFailure(
            GateCode.E_CONSENT_PROOF,
            f"{verb} must come from the EiraOS app (missing or invalid consent proof)",
        )

    def _human_actor(self, session_id: str | None) -> dict[str, Any] | None:
        """Consent and confirmation come from the user, never from the model."""
        actor = self._actor(session_id)
        if actor is None or actor["caller_model"]:
            return None
        return actor

    def _store_pending(
        self,
        raw: str | bytes | None,
        envelope: dict[str, Any],
        digest: str,
        policy: ActionPolicy,
        origin: Origin,
        session_id: str | None,
        actor: dict[str, Any] | None,
        rendering: Any,
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
                "rendering_text": rendering.text,
                "rendering_hash": rendering.hash,
                "renderer_version": rendering.version,
                "render_lang": rendering.lang,
            }
        )
        record = self.store.find(envelope["id"])
        assert record is not None
        if not inserted and (
            record["content_hash"] != digest
            or record["actor_identity"] != (actor["identity"] if actor else "")
            or record["render_lang"] != rendering.lang
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

    def _rendering_hash_of(self, action_id: str | None) -> str | None:
        record = self.store.find(action_id) if action_id else None
        return record.get("rendering_hash") if record else None

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
                "rendering_hash": self._rendering_hash_of(result.action_id),
                "policy_version": POLICY_VERSION,
                # Which process asked (SO_PEERCRED), so audit and SIEM can tell
                # the model from the user (bilag A pkt. 1).
                "caller": _caller_audit(),
                # Which delegation let the model propose (None for humans).
                "delegation": _DELEGATION.get(),
                **_rights_audit(),
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


def _rendering(record: dict[str, Any]) -> dict[str, Any] | None:
    if not record.get("rendering_hash"):
        return None
    return {
        "text": record["rendering_text"],
        "hash": record["rendering_hash"],
        "lang": record["render_lang"],
        "version": record["renderer_version"],
    }


def _rendering_intact(record: dict[str, Any]) -> bool:
    """The stored text still hashes to the stored rendering hash. The text is
    never re-rendered: a newer renderer must not change what was consented to."""
    if not record.get("rendering_hash") or record.get("rendering_text") is None:
        return False
    expected = rendering_hash(record["rendering_text"], record["render_lang"], record["renderer_version"])
    return expected == record["rendering_hash"]


def _boot_instant(consent: dict[str, Any]) -> BootInstant | None:
    if consent.get("boot_id") is None or consent.get("boottime_ns") is None:
        return None
    return BootInstant(consent["boot_id"], int(consent["boottime_ns"]))


# Set by layer 6 for the audit entry of the same call. Context variables are
# per thread and per task, so concurrent requests never see each other's.
_RIGHTS: contextvars.ContextVar[ActiveRights | None] = contextvars.ContextVar("gate_rights", default=None)
_DELEGATION: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "gate_delegation", default=None
)
_DECISION: contextvars.ContextVar[contract.Decision | None] = contextvars.ContextVar(
    "gate_rights_decision", default=None
)


_MODEL_CANNOT_DECIDE = LayerFailure(
    GateCode.E_MODEL_CANNOT_DECIDE, "the model proposes; only the user consents and confirms"
)


def _caller_audit() -> dict[str, Any] | None:
    caller = current_caller()
    return None if caller is None else {"uid": caller.uid, "pid": caller.pid, "model": caller.model}


def _model_is_calling() -> bool:
    caller = current_caller()
    return caller is not None and caller.model


def _reset_rights() -> None:
    _RIGHTS.set(None)
    _DECISION.set(None)
    _DELEGATION.set(None)


def action_key(action_type: str) -> str:
    """Gate action type → rights-set action key (RIGHTS-SET §2.2)."""
    return action_type if action_type.startswith("system:") else f"edp:{action_type}"


def _rights_audit() -> dict[str, Any]:
    """ADR-0003: every decision records which signed set it rested on, and
    whether the owner has root (then the gate protects against mistakes and
    the model and other OS users, not against the owner)."""
    rights = _RIGHTS.get()
    if rights is None:
        return {"rights_set_id": None}
    entry = rights.audit()
    decision = _DECISION.get()
    if decision is not None and decision.allowed:
        entry["rights_grant"] = decision.grant_index
    return entry
