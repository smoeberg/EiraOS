"""Lag 1–3: syntaks, schema og semantik for EDP 1.0-handlinger."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from jsonschema import Draft202012Validator

from app.gate.errors import GateCode, LayerFailure

MAX_INPUT_BYTES = 256 * 1024
SCHEMA_PATH = Path(__file__).with_name("edp-1.0.schema.json")

# Conversations are anchored to objects, never to channels (EDP §2.1).
CONVERSATION_ID = re.compile(r"^obj:[a-z][a-z0-9_]*:[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
# Supported identity syntaxes. Syntax is not proof of ownership.
IDENTITY = re.compile(
    r"^(did:eira:[a-z0-9][a-z0-9_.-]{0,99}"
    r"|external:(sms|email|xmpp|matrix|sip):[^\s]{1,320})$"
)

REFERENCE_FIELDS = {
    "commitment_accepted": "commitment_id",
    "commitment_declined": "commitment_id",
}


class ActionLookup(Protocol):
    def find(self, action_id: str) -> dict[str, Any] | None:
        """Stored action record (with ``conversation_id`` and ``action_type``)."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-standard JSON constant {name}")


def parse_json(raw: str | bytes | None) -> dict[str, Any]:
    """Lag 1, fælles for begge handlingsfamilier: gyldig JSON-objekt."""
    if raw is None:
        raise LayerFailure(GateCode.E_SYNTAX, "no input (model runtime unavailable?)")
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if len(raw) > MAX_INPUT_BYTES:
        raise LayerFailure(GateCode.E_SYNTAX, "input too large")
    try:
        text = raw.decode("utf-8")
        envelope = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise LayerFailure(GateCode.E_SYNTAX, f"invalid JSON: {error}") from None
    if not isinstance(envelope, dict):
        raise LayerFailure(GateCode.E_SYNTAX, "a gate action must be a JSON object")
    return envelope


def layer1_syntax(raw: str | bytes | None) -> dict[str, Any]:
    """Lag 1: gyldig JSON, EDP-version og obligatoriske felter."""
    return edp_syntax(parse_json(raw))


def edp_syntax(envelope: dict[str, Any]) -> dict[str, Any]:
    if envelope.get("edp") != "1.0":
        raise LayerFailure(GateCode.E_SYNTAX, 'edp must be "1.0"')
    for name in ("id", "conversation_id", "participants", "action"):
        if name not in envelope:
            raise LayerFailure(GateCode.E_SYNTAX, f"missing required field {name}")
    temporal = envelope.get("temporal")
    if not isinstance(temporal, dict) or "created_at" not in temporal:
        raise LayerFailure(GateCode.E_SYNTAX, "missing required field temporal.created_at")
    return envelope


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def parse_time(value: Any, name: str) -> datetime:
    """RFC 3339 timestamp with an explicit timezone."""
    if not isinstance(value, str):
        raise LayerFailure(GateCode.E_SCHEMA, f"{name} must be an RFC 3339 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise LayerFailure(GateCode.E_SCHEMA, f"{name} is not RFC 3339") from None
    if parsed.tzinfo is None:
        raise LayerFailure(GateCode.E_SCHEMA, f"{name} needs a timezone")
    return parsed


def layer2_schema(envelope: dict[str, Any]) -> None:
    """Lag 2: lukket taksonomi, indhold pr. type, identiteter, transport, veritas."""
    errors = sorted(_validator().iter_errors(envelope), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        where = "/".join(str(p) for p in first.path) or "(root)"
        raise LayerFailure(GateCode.E_SCHEMA, f"{where}: {first.message}")
    if not CONVERSATION_ID.match(envelope["conversation_id"]):
        raise LayerFailure(GateCode.E_SCHEMA, "conversation_id must be an object reference (obj:<type>:<id>)")
    for participant in envelope["participants"]:
        if not IDENTITY.match(participant["identity"]):
            raise LayerFailure(GateCode.E_SCHEMA, f"unsupported identity syntax: {participant['identity']!r}")
    content = envelope["action"]["content"]
    for name in ("when", "until"):
        if name in content:
            parse_time(content[name], f"action.content.{name}")
    temporal = envelope["temporal"]
    parse_time(temporal["created_at"], "temporal.created_at")
    if temporal.get("valid_from") is not None:
        parse_time(temporal["valid_from"], "temporal.valid_from")


def layer3_semantics(envelope: dict[str, Any], actions: ActionLookup) -> None:
    """Lag 3: feltkonsistens, temporal konsistens og supersedes."""
    action = envelope["action"]
    action_type = action["type"]
    content = action["content"]
    conversation = envelope["conversation_id"]

    ref_field = REFERENCE_FIELDS.get(action_type)
    if ref_field:
        target = actions.find(content[ref_field])
        if target is None or target["action_type"] != "commitment_proposed":
            raise LayerFailure(GateCode.E_SEMANTIC, f"{ref_field} does not reference a proposed commitment")
        if target["conversation_id"] != conversation:
            raise LayerFailure(GateCode.E_SEMANTIC, f"{ref_field} belongs to another conversation")

    temporal = envelope["temporal"]
    created = parse_time(temporal["created_at"], "temporal.created_at")
    if temporal.get("valid_from") is not None:
        if parse_time(temporal["valid_from"], "temporal.valid_from") < created:
            raise LayerFailure(GateCode.E_SEMANTIC, "valid_from is before created_at")

    supersedes = temporal.get("supersedes")
    if supersedes is not None:
        target = actions.find(supersedes)
        if target is None or target["conversation_id"] != conversation:
            raise LayerFailure(
                GateCode.E_SEMANTIC, "supersedes must reference an action in the same conversation"
            )

    # Needed to understand the action but not derivable: ask, don't guess.
    if action_type == "utterance" and not content["text"].strip():
        raise LayerFailure(GateCode.E_MISSING_FIELD, "the message has no text", clarify=True)
    if action_type == "commitment_proposed" and not content["what"].strip():
        raise LayerFailure(GateCode.E_MISSING_FIELD, "what is being proposed?", clarify=True)


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def content_hash(envelope: dict[str, Any]) -> str:
    """Hash of everything a confirmation or consent covers.

    Binds the conversation, the participants and the action (type and every
    content parameter). Transport and veritas are excluded: they are enriched
    by intentd/adapters after the user decided, and may not change the action.
    """
    material = {
        "id": envelope["id"],
        "conversation_id": envelope["conversation_id"],
        "participants": envelope["participants"],
        "action": envelope["action"],
        "valid_from": envelope["temporal"].get("valid_from"),
    }
    return "sha256:" + hashlib.sha256(canonical_json(material)).hexdigest()


def input_hash(raw: str | bytes | None) -> str:
    if raw is None:
        raw = b""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()
