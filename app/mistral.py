from __future__ import annotations

import json
import os

import httpx

from app.models import AgencyContext, IntentCategory

OLLAMA_URL = os.getenv("EIRA_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("EIRA_OLLAMA_MODEL", "mistral")

ACTION_CATEGORY_MAP: dict[str, IntentCategory] = {
    "approve": IntentCategory.DECISION,
    "reject": IntentCategory.DECISION,
    "postpone": IntentCategory.DECISION,
    "read": IntentCategory.INFORMATION,
    "search": IntentCategory.INFORMATION,
    "status": IntentCategory.INFORMATION,
    "send": IntentCategory.ACTION,
    "create": IntentCategory.ACTION,
    "switch_focus": IntentCategory.ACTION,
    "explore": IntentCategory.DISCUSSION,
    "clarify": IntentCategory.DISCUSSION,
}

VALID_ACTIONS = set(ACTION_CATEGORY_MAP.keys())


def is_mistral_available() -> bool:
    try:
        with httpx.Client(timeout=2.0) as client:
            response = client.get(f"{OLLAMA_URL}/api/tags")
            if response.status_code != 200:
                return False
            models = response.json().get("models", [])
            names = {m.get("name", "").split(":")[0] for m in models}
            return OLLAMA_MODEL in names or any(OLLAMA_MODEL in n for n in names)
    except (httpx.HTTPError, json.JSONDecodeError):
        return False


def parse_with_mistral(raw_input: str, focus: str) -> dict | None:
    if not is_mistral_available():
        return None

    prompt = f"""Du er EIRA Intent Engine. Parse denne danske arbejdsintention.
Fokus: {focus}

Returner KUN valid JSON med felter:
- category: DECISION|DISCUSSION|INFORMATION|ACTION|RELATION
- action: approve|reject|postpone|read|search|status|send|create|switch_focus|explore|clarify
- confidence: float 0.0-1.0
- rationale: kort dansk forklaring

Bruger: "{raw_input}"
"""

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
            )
            if response.status_code != 200:
                return None
            body = response.json()
            text = body.get("response", "").strip()
            if not text:
                return None
            parsed = json.loads(text)
            action = str(parsed.get("action", "search")).lower()
            if action not in VALID_ACTIONS:
                action = "search"
            category_raw = str(parsed.get("category", "INFORMATION")).upper()
            try:
                category = IntentCategory(category_raw)
            except ValueError:
                category = ACTION_CATEGORY_MAP.get(action, IntentCategory.INFORMATION)
            confidence = float(parsed.get("confidence", 0.7))
            confidence = max(0.0, min(1.0, confidence))
            return {
                "category": category,
                "action": action,
                "confidence": confidence,
                "rationale": str(parsed.get("rationale", "Mistral parse")),
                "parse_mode": "mistral",
            }
    except (httpx.HTTPError, json.JSONDecodeError, ValueError, TypeError):
        return None


def build_agency(
    actor_id: str,
    actor_name: str,
    org_unit: str,
    assurance_level: str,
) -> AgencyContext:
    delegated_for = None
    if "økonomi" in org_unit.lower() or "skole" in org_unit.lower():
        delegated_for = org_unit
    return AgencyContext(
        actor_id=actor_id,
        actor_name=actor_name,
        org_unit=org_unit,
        assurance_level=assurance_level,
        delegated_for=delegated_for,
    )

