from __future__ import annotations

import json
import re
import uuid

from app.capability import find_capability_match, infer_resource
from app.database import get_connection, utc_now_iso
from app.mistral import (
    ACTION_CATEGORY_MAP,
    build_agency,
    parse_with_mistral,
)
from app.models import (
    AgencyContext,
    IntentCategory,
    IntentStatus,
    ParseIntentRequest,
    PlannedIntent,
    ParsedIntent,
    TrustItem,
    score_to_trust_level,
)

RULES: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"godkend|approve", re.I), "approve", 0.92),
    (re.compile(r"afvis|reject", re.I), "reject", 0.90),
    (re.compile(r"status|hvad venter", re.I), "status", 0.85),
    (re.compile(r"send", re.I), "send", 0.80),
    (re.compile(r"skift fokus", re.I), "switch_focus", 0.88),
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
        block_reason = f"Ingen adapter understøtter {intent.action} på {intent.resource}"
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
