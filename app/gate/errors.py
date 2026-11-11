"""Beslutningsmodel og fejlkoder (Gate Kernel 1.0 §4–5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

GATE_VERSION = "1.1"  # 1.1: EiraSystemAPI family (ADR-0002)


class Decision(str, Enum):
    PASS = "PASS"
    REJECT = "REJECT"
    CLARIFY = "CLARIFY"


class GateCode(str, Enum):
    E_SYNTAX = "E_SYNTAX"
    E_SCHEMA = "E_SCHEMA"
    E_SEMANTIC = "E_SEMANTIC"
    E_MISSING_FIELD = "E_MISSING_FIELD"
    E_POLICY = "E_POLICY"
    E_CONSENT = "E_CONSENT"
    E_NEED_CONSENT = "E_NEED_CONSENT"
    E_UNAUTHORIZED = "E_UNAUTHORIZED"
    # The model tried to consent or confirm. Its own code so audit, SIEM and
    # Fleet can alert on it: it is either a UI bug or a compromised model call.
    E_MODEL_CANNOT_DECIDE = "E_MODEL_CANNOT_DECIDE"
    # Consent/confirm without the proof only the EiraOS app can make: another
    # program running as the user, or a stolen session id (bilag A pkt. 1).
    E_CONSENT_PROOF = "E_CONSENT_PROOF"
    E_STEP_UP_REQUIRED = "E_STEP_UP_REQUIRED"
    E_STATE = "E_STATE"
    E_PARTIAL = "E_PARTIAL"
    E_EXECUTOR_UNAVAILABLE = "E_EXECUTOR_UNAVAILABLE"


# Layer each code belongs to; CLARIFY is only legal in layers 1–3.
CODE_LAYER = {
    GateCode.E_SYNTAX: 1,
    GateCode.E_SCHEMA: 2,
    GateCode.E_SEMANTIC: 3,
    GateCode.E_MISSING_FIELD: 3,
    GateCode.E_POLICY: 4,
    GateCode.E_CONSENT: 5,
    GateCode.E_NEED_CONSENT: 5,
    GateCode.E_UNAUTHORIZED: 6,
    GateCode.E_MODEL_CANNOT_DECIDE: 5,
    GateCode.E_CONSENT_PROOF: 5,
    GateCode.E_STEP_UP_REQUIRED: 6,
    GateCode.E_STATE: 7,
    GateCode.E_PARTIAL: 8,
    GateCode.E_EXECUTOR_UNAVAILABLE: 8,
}


class LayerFailure(Exception):
    """Raised inside the gate to stop at the failing layer."""

    def __init__(
        self,
        code: GateCode,
        detail: str,
        *,
        clarify: bool = False,
        data: dict[str, Any] | None = None,
    ) -> None:
        layer = CODE_LAYER[code]
        if clarify and layer > 3:
            raise ValueError("CLARIFY is only allowed in layers 1-3")
        self.code = code
        self.layer = layer
        self.detail = detail
        self.decision = Decision.CLARIFY if clarify else Decision.REJECT
        self.data = data or {}
        super().__init__(f"{code.value}: {detail}")


@dataclass(frozen=True)
class GateResult:
    """What the gate tells its caller. ``state`` is the action's honest state."""

    decision: Decision | None
    action_id: str | None = None
    layer: int | None = None
    code: GateCode | None = None
    detail: str = ""
    state: str | None = None
    content_hash: str | None = None
    execution_id: str | None = None
    result: dict[str, Any] | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": GATE_VERSION,
            "decision": self.decision.value if self.decision else None,
            "action_id": self.action_id,
            "layer": self.layer,
            "error": self.code.value if self.code else None,
            "detail": self.detail,
            "state": self.state,
            "content_hash": self.content_hash,
            "execution_id": self.execution_id,
            "result": self.result,
            **({"data": self.data} if self.data else {}),
        }
