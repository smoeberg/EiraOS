"""AI-INTERFACE-1.0 §3–§4 and §7: the adapter contract and its checks.

The checks here are what the model process trusts, not the adapter: an
adapter's output that does not follow the contract becomes
``E_INVALID_OUTPUT``, never a guessed action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

E_MODEL_UNAVAILABLE = "E_MODEL_UNAVAILABLE"
E_INVALID_OUTPUT = "E_INVALID_OUTPUT"
E_UNSUPPORTED_LANGUAGE = "E_UNSUPPORTED_LANGUAGE"
E_CONTEXT_TOO_LARGE = "E_CONTEXT_TOO_LARGE"

SUPPORTED_LANGUAGES = ("da", "de", "en")
MAX_TEXT = 4000
MAX_PARTICIPANTS = 50


@dataclass(frozen=True)
class Participant:
    identity: str
    role: str
    name: str = ""


@dataclass(frozen=True)
class ConversationContext:
    """Read-only (§6). Given by the app; the model never changes it."""

    conversation_id: str
    participants: tuple[Participant, ...]
    now: str  # ISO 8601, the reference for "i morgen" and the like


@dataclass(frozen=True)
class IntentExtraction:
    intent: str
    entities: dict[str, Any]
    language: str
    confidence: float


@dataclass(frozen=True)
class EdpAction:
    """Only ``type`` and ``content`` (§3.2): no transport, veritas or
    supersedes; the model process adds neutral defaults, not the adapter."""

    type: str
    content: dict[str, Any]
    participants: tuple[Participant, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Abstain:
    reason: str


@dataclass(frozen=True)
class ModelError:
    code: str
    detail: str = ""


class ModelAdapter(Protocol):
    name: str
    version: str

    def health(self) -> dict[str, Any]: ...

    def extract_intent(
        self, text: str, context: ConversationContext, language_hint: str | None
    ) -> IntentExtraction | Abstain | ModelError: ...

    def propose_action(
        self, intent: IntentExtraction, allowed_actions: tuple[str, ...], context: ConversationContext
    ) -> EdpAction | Abstain | ModelError: ...


def checked_extraction(result: Any) -> IntentExtraction | Abstain | ModelError:
    if isinstance(result, (Abstain, ModelError)):
        return result
    if (
        not isinstance(result, IntentExtraction)
        or not isinstance(result.intent, str)
        or not isinstance(result.entities, dict)
        or result.language not in SUPPORTED_LANGUAGES
        or not 0.0 <= float(result.confidence) <= 1.0
    ):
        return ModelError(E_INVALID_OUTPUT, "extract_intent broke the contract")
    return result


def checked_action(result: Any, allowed: tuple[str, ...], context: ConversationContext) -> EdpAction | Abstain | ModelError:
    if isinstance(result, (Abstain, ModelError)):
        return result
    if not isinstance(result, EdpAction) or not isinstance(result.content, dict):
        return ModelError(E_INVALID_OUTPUT, "propose_action broke the contract")
    if result.type not in allowed:
        # §3.2: the model refuses actions outside the list itself (and the
        # gate would too).
        return Abstain("no_matching_action")
    known = {p.identity for p in context.participants}
    if any(p.identity not in known for p in result.participants):
        # The model may only address people the app put in the context.
        return ModelError(E_INVALID_OUTPUT, "participant outside the context")
    return result
