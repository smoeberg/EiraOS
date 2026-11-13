"""A deterministic adapter (AI-INTERFACE-1.0 §4) for Danish commands.

It needs no model weights and no network, so the packaged model process
works on every installation and in CI. It recognises a few clear commands
and abstains on everything else (§3.1: "ikke gætte"). A language model
adapter can replace it behind the same contract.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.model.contract import (
    E_UNSUPPORTED_LANGUAGE,
    Abstain,
    ConversationContext,
    EdpAction,
    IntentExtraction,
    ModelError,
    Participant,
)

SEND = re.compile(
    r"^\s*(?:send|skriv)(?:\s+en)?(?:\s+besked)?\s+til\s+(?P<who>[^:,]+?)\s*[:,]\s*(?P<text>\S.*)$",
    re.IGNORECASE | re.DOTALL,
)
MEETING = re.compile(
    r"^\s*(?:aftal|foreslå|book)\s+(?:et\s+)?møde\s+med\s+(?P<who>\S+)\s+(?P<when>.+?)\s+om\s+(?P<topic>\S.*)$",
    re.IGNORECASE | re.DOTALL,
)
# Power (EiraSystemAPI, ADR-0002). Whole sentence only: "sluk lyset" is not
# a request to turn the computer off.
_MACHINE = r"(?:\s+(?:for\s+)?(?:computeren|maskinen|pc'en|pcen))?"
POWER = (
    (re.compile(rf"^\s*(?:sluk|luk\s+ned){_MACHINE}\s*[.!]?\s*$", re.IGNORECASE), "poweroff"),
    (re.compile(rf"^\s*(?:genstart){_MACHINE}\s*[.!]?\s*$", re.IGNORECASE), "reboot"),
    (re.compile(rf"^\s*(?:sæt{_MACHINE}\s+i\s+dvale|dvale){_MACHINE}\s*[.!]?\s*$", re.IGNORECASE),
     "suspend"),
)
WHEN_DATE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\s+kl\.?\s*(?P<h>\d{1,2})(?:[:.](?P<m>\d{2}))?$", re.IGNORECASE)
WHEN_REL = re.compile(r"^(?P<day>i\s+dag|i\s+morgen)\s+kl\.?\s*(?P<h>\d{1,2})(?:[:.](?P<m>\d{2}))?$", re.IGNORECASE)


def _person(who: str, context: ConversationContext) -> Participant | None:
    """Only someone in the context, matched by name or identity. Two matches
    is ambiguous, not a choice."""
    wanted = who.strip().lower()
    found = [
        p for p in context.participants
        if p.name.lower() == wanted
        or p.identity.lower() == wanted
        or p.identity.lower().rsplit(".", 1)[-1] == wanted
        or p.identity.lower().rsplit(":", 1)[-1] == wanted
    ]
    return found[0] if len(found) == 1 else None


def _when(raw: str, now: str) -> str | None:
    base = datetime.fromisoformat(now.replace("Z", "+00:00"))
    text = raw.strip().lower()
    if match := WHEN_DATE.match(text):
        day = datetime.fromisoformat(match["date"]).date()
    elif match := WHEN_REL.match(text):
        day = base.date() + timedelta(days=0 if match["day"].replace(" ", "") == "idag" else 1)
    else:
        return None
    hour, minute = int(match["h"]), int(match["m"] or 0)
    if hour > 23 or minute > 59:
        return None
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=base.tzinfo).isoformat()


class RuleAdapter:
    name = "eira-rules"
    version = "1.0"

    def health(self) -> dict[str, object]:
        return {"ok": True, "detail": "deterministic rules, no model weights"}

    def extract_intent(
        self, text: str, context: ConversationContext, language_hint: str | None
    ) -> IntentExtraction | Abstain | ModelError:
        if language_hint not in (None, "da"):
            return ModelError(E_UNSUPPORTED_LANGUAGE, "the rule adapter reads Danish only")
        for pattern, action in POWER:
            if pattern.match(text):
                return IntentExtraction("power", {"action": action}, "da", 0.95)
        if match := SEND.match(text):
            person = _person(match["who"], context)
            if person is None:
                return Abstain("unknown_person")
            return IntentExtraction("send_message", {"person": person.identity, "text": match["text"].strip()},
                                    "da", 0.9)
        if match := MEETING.match(text):
            person = _person(match["who"], context)
            when = _when(match["when"], context.now)
            if person is None:
                return Abstain("unknown_person")
            if when is None:
                return Abstain("ambiguous_input")
            return IntentExtraction("schedule_meeting",
                                    {"person": person.identity, "when": when, "topic": match["topic"].strip()},
                                    "da", 0.85)
        return Abstain("ambiguous_input")

    def propose_action(
        self, intent: IntentExtraction, allowed_actions: tuple[str, ...], context: ConversationContext
    ) -> EdpAction | Abstain | ModelError:
        if intent.intent == "power" and "system:power.request_action" in allowed_actions:
            return EdpAction("system:power.request_action", {"action": intent.entities["action"]})
        addressed = tuple(p for p in context.participants if p.identity == intent.entities.get("person"))
        if intent.intent == "send_message" and "utterance" in allowed_actions:
            return EdpAction("utterance", {"text": intent.entities["text"], "lang": "da"}, addressed)
        if intent.intent == "schedule_meeting" and "commitment_proposed" in allowed_actions:
            return EdpAction("commitment_proposed",
                             {"what": intent.entities["topic"], "when": intent.entities["when"]}, addressed)
        return Abstain("no_matching_action")
