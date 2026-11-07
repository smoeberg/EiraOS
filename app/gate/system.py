"""Handlingsfamilien EiraSystemAPI (Gate 1.1, ADR-0002).

Kontrollerede, typede operationer på operativsystemet. De går gennem de
samme otte lag, den samme policy, det samme samtykke, den samme audit og
den samme recovery som EDP. Familien har sit eget skema, men ingen egen
sikkerhedsmodel.

Wire-form (én JSON-genstand)::

    {"eira_system": "1", "id": "sys-…", "operation": "power.request_action",
     "input": {"action": "poweroff"}, "created_at": "2026-11-07T10:00:00Z"}

* Listen over operationer er lukket. En ukendt operation giver ``E_SCHEMA``.
* Hver operation har et skema uden ekstra felter og en post i gatens
  policy-registry (``system:<operation>``). Modellen kan foreslå en
  operation, men ikke vælge dens reversibilitet eller rettigheder.
* Omfanget er altid den lokale enhed (``device:local``). Den handlende er
  sessionens bruger; et forslag kan ikke handle på vegne af andre.
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from app.gate.errors import GateCode, LayerFailure

SYSTEM_VERSION = "1"
SYSTEM_SCOPE = "device:local"
TYPE_PREFIX = "system:"

_ENVELOPE_FIELDS = {"eira_system", "id", "operation", "input", "created_at"}

# Closed list of operations. Read-only operations stay in Tauri's
# eira_system; only state-changing ones exist here.
OPERATIONS: dict[str, dict[str, Any]] = {
    "power.request_action": {
        "type": "object",
        "additionalProperties": False,
        "required": ["action"],
        "properties": {"action": {"enum": ["poweroff", "reboot", "suspend"]}},
    },
}

_VALIDATORS = {name: Draft202012Validator(schema) for name, schema in OPERATIONS.items()}


def is_system_request(obj: dict[str, Any]) -> bool:
    return "eira_system" in obj


def syntax(obj: dict[str, Any]) -> None:
    """Lag 1 for familien: version og obligatoriske felter."""
    if "edp" in obj:
        raise LayerFailure(GateCode.E_SYNTAX, "an action cannot belong to two families")
    if obj.get("eira_system") != SYSTEM_VERSION:
        raise LayerFailure(GateCode.E_SYNTAX, f'eira_system must be "{SYSTEM_VERSION}"')
    for name in ("id", "operation", "input", "created_at"):
        if name not in obj:
            raise LayerFailure(GateCode.E_SYNTAX, f"missing required field {name}")


def schema(obj: dict[str, Any]) -> None:
    """Lag 2: lukket liste af operationer, typet input, ingen ekstra felter."""
    from app.gate.edp import parse_time

    extra = set(obj) - _ENVELOPE_FIELDS
    if extra:
        raise LayerFailure(GateCode.E_SCHEMA, f"unknown fields: {sorted(extra)}")
    action_id = obj["id"]
    if not isinstance(action_id, str) or not 0 < len(action_id) <= 200:
        raise LayerFailure(GateCode.E_SCHEMA, "id must be a string of 1-200 characters")
    operation = obj["operation"]
    validator = _VALIDATORS.get(operation) if isinstance(operation, str) else None
    if validator is None:
        raise LayerFailure(GateCode.E_SCHEMA, f"unknown system operation {operation!r}")
    errors = sorted(validator.iter_errors(obj["input"]), key=lambda e: list(e.path))
    if errors:
        raise LayerFailure(GateCode.E_SCHEMA, f"input: {errors[0].message}")
    parse_time(obj["created_at"], "created_at")


def view(obj: dict[str, Any], actor_identity: str) -> dict[str, Any]:
    """The request in the gate's common action shape.

    The acting participant is the session's user, never a field in the
    request, so the content hash binds the action to who proposed it.
    """
    return {
        "id": obj["id"],
        "conversation_id": SYSTEM_SCOPE,
        "participants": [{"identity": actor_identity, "role": "member"}],
        "action": {"type": TYPE_PREFIX + obj["operation"], "content": obj["input"]},
        "temporal": {"created_at": obj["created_at"], "valid_from": None, "supersedes": None},
        "family": "system",
    }


SENTENCES = {
    "da": {
        "power.request_action": {
            "poweroff": "Sluk computeren",
            "reboot": "Genstart computeren",
            "suspend": "Sæt computeren i dvale",
        },
        "where": "på denne enhed",
        "warning": "Ikke-gemt arbejde i åbne programmer kan gå tabt.",
    },
    "en": {
        "power.request_action": {
            "poweroff": "Shut down the computer",
            "reboot": "Restart the computer",
            "suspend": "Suspend the computer",
        },
        "where": "on this device",
        "warning": "Unsaved work in open programs may be lost.",
    },
}


def sentence(operation: str, content: dict[str, Any], lang: str) -> list[str]:
    words = SENTENCES[lang]
    head = f"{words[operation][content['action']]} {words['where']}."
    lines = [head]
    if operation == "power.request_action" and content["action"] in ("poweroff", "reboot"):
        lines.append(words["warning"])
    return lines
