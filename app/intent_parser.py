from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from app.capability import find_capability_match, infer_resource
from app.core.state import ProposalState, State
from app.database import get_connection, utc_now_iso
from app.mistral import (
    ACTION_CATEGORY_MAP,
    build_agency,
    parse_with_mistral,
)
from app.models import (
    IntentCategory,
    IntentStatus,
    ParsedIntent,
    ParseIntentRequest,
    PlannedIntent,
    TrustItem,
    score_to_trust_level,
)

RULES: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"godkend|approve", re.IGNORECASE), "approve", 0.92),
    (re.compile(r"afvis|reject", re.IGNORECASE), "reject", 0.90),
    (re.compile(r"status|hvad venter", re.IGNORECASE), "status", 0.85),
    (re.compile(r"send", re.IGNORECASE), "send", 0.80),
    (re.compile(r"skift fokus", re.IGNORECASE), "switch_focus", 0.88),
]


def _parse_with_rules(raw_input: str, focus: str) -> dict:
    action = "search"
    confidence = 0.45
    rationale = f"Fokus: {focus}. Ingen specifik handling fundet — afklaring anbefales."

    for pattern, mapped_action, rule_confidence in RULES:
        if pattern.search(raw_input):
            action = mapped_action
            confidence = rule_confidence
            rationale = f"Rule-based parse: '{action}' med confidence {confidence:.0%}."
            break

    category = ACTION_CATEGORY_MAP.get(action, IntentCategory.INFORMATION)
    return {
        "category": category,
        "action": action,
        "confidence": confidence,
        "rationale": rationale,
        "parse_mode": "rule",
    }


def parse_intent_request(body: ParseIntentRequest) -> ParsedIntent:
    agency = build_agency(
        body.actor_id,
        body.actor_name,
        body.org_unit,
        body.assurance_level,
    )

    parsed = None
    if body.use_mistral:
        parsed = parse_with_mistral(body.raw_input, body.focus)
    if not parsed:
        parsed = _parse_with_rules(body.raw_input, body.focus)

    action = parsed["action"]
    category = parsed["category"]
    confidence = parsed["confidence"]
    rationale = parsed["rationale"]
    parse_mode = parsed["parse_mode"]

    resource = infer_resource(action, body.raw_input)
    trust_score = int(confidence * 100)
    trust_level = score_to_trust_level(trust_score)

    journey_id = None
    required_assurance = None
    status = IntentStatus.CONFIRMATION_NEEDED

    if action == "approve":
        journey_id = _find_journey_for_budget()
        required_assurance = "org_acting"
        trust_score = max(trust_score, 71)
        trust_level = score_to_trust_level(trust_score)
        rationale = (
            f"{rationale} Budget i aktivt fokus. Kræver org_acting (MitID Erhverv)."
        )
        status = IntentStatus.PENDING_CONFIRMATION
    elif confidence >= 0.6:
        status = IntentStatus.PENDING_CONFIRMATION

    capability_match = find_capability_match(action, resource, agency)
    if capability_match and capability_match.required_assurance:
        required_assurance = capability_match.required_assurance

    intent = ParsedIntent(
        intent_id=str(uuid.uuid4()),
        raw_input=body.raw_input,
        category=category,
        action=action,
        confidence=confidence,
        trust_level=trust_level,
        trust_score=trust_score,
        journey_id=journey_id,
        required_assurance=required_assurance,
        status=status,
        rationale=rationale,
        parse_mode=parse_mode,
        agency=agency,
        capability_match=capability_match,
        resource=resource,
    )
    _emit_audit("intent.parsed", intent.model_dump(mode="json"))
    return intent


def plan_intent(body: ParseIntentRequest) -> PlannedIntent:
    intent = parse_intent_request(body)
    can_execute = True
    block_reason = None

    if intent.status == IntentStatus.CONFIRMATION_NEEDED:
        can_execute = False
        block_reason = "Lav confidence — afklaring påkrævet"
    elif not intent.capability_match:
        can_execute = False
        block_reason = (
            f"Ingen adapter understøtter {intent.action} på {intent.resource}"
        )
    elif not intent.capability_match.assurance_met:
        can_execute = False
        block_reason = (
            f"Kræver {intent.capability_match.required_assurance}, "
            f"har {intent.agency.assurance_level if intent.agency else 'ukendt'}"
        )

    planned = PlannedIntent(
        **intent.model_dump(),
        can_execute=can_execute,
        block_reason=block_reason,
    )
    _emit_audit("intent.planned", planned.model_dump(mode="json"))
    return planned


def parse_intent(raw_input: str, focus: str) -> ParsedIntent:
    return parse_intent_request(
        ParseIntentRequest(raw_input=raw_input, focus=focus, use_mistral=True)
    )


def _find_journey_for_budget() -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM journeys WHERE title LIKE '%Budget%' AND status = 'active' LIMIT 1"
        ).fetchone()
    return row["id"] if row else None


def _emit_audit(event_type: str, payload: dict) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO audit_events (id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), event_type, json.dumps(payload), utc_now_iso()),
        )


def list_trust_items() -> list[TrustItem]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM trust_items ORDER BY sort_order ASC"
        ).fetchall()
    return [
        TrustItem(
            id=row["id"],
            title=row["title"],
            summary=row["summary"],
            trust_score=row["trust_score"],
            trust_level=score_to_trust_level(row["trust_score"]),
            sources=json.loads(row["sources"]),
            object_id=row["object_id"],
        )
        for row in rows
    ]


StructuredIntentParser = Callable[[str], Mapping[str, Any] | None]


class MistralProposalParser:
    """Optional Ollama/Mistral adapter returning the strict proposal schema."""

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.endpoint = (
            endpoint or os.getenv("EIRA_OLLAMA_URL", "http://127.0.0.1:11434")
        ).rstrip("/")
        self.model = model or os.getenv("EIRA_OLLAMA_MODEL", "mistral")
        self.timeout = timeout

    def __call__(self, raw_input: str) -> Mapping[str, Any] | None:
        import httpx

        prompt = f"""Strukturér denne danske forvaltningsintention som JSON.
Returner KUN et objekt med felterne suggested_transformation, state_type,
payload, confidence_score og rationale. confidence_score skal være 0.0-1.0.
Intention: {json.dumps(raw_input, ensure_ascii=False)}
"""
        try:
            response = httpx.post(
                f"{self.endpoint}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
            parsed = json.loads(body.get("response", ""))
            return parsed if isinstance(parsed, Mapping) else None
        except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError):
            return None


def _parse_number(value: str) -> float:
    compact = value.replace(" ", "")
    if "," in compact:
        compact = compact.replace(".", "").replace(",", ".")
    elif compact.count(".") > 1 or (
        compact.count(".") == 1 and len(compact.rsplit(".", 1)[1]) == 3
    ):
        compact = compact.replace(".", "")
    return float(compact)


class IntentParser:
    """Convert free text into an immutable, content-hashed ProposalState."""

    _permit = re.compile(
        r"(?:opret|lav|ansøg om)\s+(?:en\s+)?byggetilladelse\s+(?:for|til)\s+(.+)",
        re.IGNORECASE,
    )
    _payment = re.compile(
        r"godkend.*?(?:udbetaling|betaling).*?([\d][\d., ]*)", re.IGNORECASE
    )
    _grant = re.compile(
        r"godkend.*?(?:bevilling|tilskud).*?([\d][\d., ]*)", re.IGNORECASE
    )
    _due_date = re.compile(r"\b(\d{4}-\d{2}-\d{2}(?:T[^\s]+)?)\b")

    def __init__(
        self,
        llm_parser: StructuredIntentParser | None = None,
        *,
        source_model: str = "eira-rule-parser-v1",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.llm_parser = llm_parser
        self.source_model = source_model
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @classmethod
    def from_environment(cls) -> IntentParser:
        enabled = os.getenv("EIRA_INTENT_LLM_ENABLED", "").casefold() in {
            "1",
            "true",
            "yes",
        }
        if enabled:
            return cls(llm_parser=MistralProposalParser(), source_model="mistral")
        return cls()

    def _rules(self, raw_input: str) -> dict[str, Any]:
        permit = self._permit.search(raw_input)
        if permit:
            address = permit.group(1).strip().rstrip(".!?")
            return {
                "suggested_transformation": "create_building_permit",
                "state_type": "BuildingPermitState",
                "payload": {"address": address, "status": "PROPOSED"},
                "confidence_score": 0.94,
                "rationale": f"Identificerede oprettelse af byggetilladelse for {address}.",
            }

        for pattern, transformation, state_type, label in (
            (self._payment, "approve_payment", "PaymentState", "udbetaling"),
            (self._grant, "approve_grant", "GrantState", "bevilling"),
        ):
            match = pattern.search(raw_input)
            if match:
                amount = _parse_number(match.group(1).strip())
                return {
                    "suggested_transformation": transformation,
                    "state_type": state_type,
                    "payload": {"amount": amount, "status": "PROPOSED"},
                    "confidence_score": 0.92,
                    "rationale": f"Identificerede godkendelse af {label} på {amount:g} kr.",
                }

        if re.search(r"\bindsend\b.*\bsag\b", raw_input, re.IGNORECASE):
            due = self._due_date.search(raw_input)
            payload: dict[str, Any] = {"description": raw_input, "status": "PROPOSED"}
            if due:
                payload["due_date"] = due.group(1)
            return {
                "suggested_transformation": "submit_case",
                "state_type": "CaseState",
                "payload": payload,
                "confidence_score": 0.82,
                "rationale": "Identificerede indsendelse af administrativ sag.",
            }

        return {
            "suggested_transformation": "clarify_intent",
            "state_type": "IntentClarificationState",
            "payload": {"raw_input": raw_input, "status": "CLARIFICATION_NEEDED"},
            "confidence_score": 0.35,
            "rationale": "Intentionen kunne ikke knyttes entydigt til en transformation.",
        }

    @staticmethod
    def _validate_structured(value: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "suggested_transformation",
            "payload",
            "confidence_score",
            "rationale",
        }
        if not required.issubset(value):
            raise ValueError("LLM result mangler obligatoriske felter")
        confidence = float(value["confidence_score"])
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("LLM confidence_score uden for 0.0–1.0")
        if not isinstance(value["payload"], Mapping):
            raise TypeError("LLM payload skal være et objekt")
        return {
            "suggested_transformation": str(value["suggested_transformation"]),
            "state_type": str(value.get("state_type") or "ProposalState"),
            "payload": dict(value["payload"]),
            "confidence_score": confidence,
            "rationale": str(value["rationale"]),
        }

    def parse(
        self,
        raw_input: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> ProposalState:
        if not isinstance(raw_input, str) or not raw_input.strip():
            raise ValueError("raw_input is required")
        structured: dict[str, Any] | None = None
        source_model = self.source_model
        if self.llm_parser is not None:
            candidate = self.llm_parser(raw_input)
            if candidate is not None:
                structured = self._validate_structured(candidate)
                source_model = (
                    "mistral"
                    if self.source_model == "eira-rule-parser-v1"
                    else self.source_model
                )
        if structured is None:
            structured = self._rules(raw_input)

        payload = dict(structured["payload"])
        if context:
            payload.setdefault("intent_context", dict(context))
        payload.setdefault("raw_input", raw_input.strip())
        state = State(
            type=structured["state_type"],
            payload=payload,
            timestamp_ns=int(self.clock().timestamp() * 1e9),
        )
        return ProposalState(
            suggested_transformation=structured["suggested_transformation"],
            candidate_state=state,
            confidence_score=structured["confidence_score"],
            source_model=source_model,
            rationale=structured["rationale"],
        )

    parse_to_proposal = parse
