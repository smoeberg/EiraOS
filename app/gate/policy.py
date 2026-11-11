"""Versionsstyret Gate-policy registry (Gate Kernel 1.0 §3.4 og §6).

Reversibilitetsklassen er intern Gate-metadata. Den læses aldrig fra
modeloutput eller EDP-payloaden. Mangler en handlingstype i registret,
behandles den som ``irreversible`` og er ikke tilladt. Ændringer her kræver
policy review og tests (``tests/test_gate_kernel.py``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from app.gate.errors import GateCode, LayerFailure

POLICY_VERSION = "2026.11"


class Reversibility(str, Enum):
    IDEMPOTENT = "idempotent"
    COMPENSABLE = "compensable"
    IRREVERSIBLE = "irreversible"


class Origin(str, Enum):
    """Who put the action in front of the gate."""

    MODEL = "model"  # EiraAI proposal
    USER = "user"  # the user's own action through the UI


@dataclass(frozen=True)
class ActionPolicy:
    action_type: str
    reversibility: Reversibility
    allowed_origins: frozenset[Origin]
    required_assurance: str = "none"
    # Registered compensating action type, required for COMPENSABLE.
    compensation: str | None = None
    limits: dict[str, Any] = field(default_factory=dict)

    @property
    def requires_consent(self) -> bool:
        return self.reversibility is Reversibility.IRREVERSIBLE

    def fingerprint(self) -> str:
        data = asdict(self)
        data["allowed_origins"] = sorted(o.value for o in self.allowed_origins)
        data["reversibility"] = self.reversibility.value
        raw = json.dumps(data, sort_keys=True, default=str).encode()
        return "sha256:" + hashlib.sha256(raw).hexdigest()


_BOTH = frozenset({Origin.MODEL, Origin.USER})

# A sent message, proposal or answer cannot be recalled: irreversible, so the
# user consents to exactly what is sent. Presence is a state that can simply
# be set again.
REGISTRY: dict[str, ActionPolicy] = {
    p.action_type: p
    for p in (
        ActionPolicy("utterance", Reversibility.IRREVERSIBLE, _BOTH),
        ActionPolicy("commitment_proposed", Reversibility.IRREVERSIBLE, _BOTH),
        ActionPolicy("commitment_accepted", Reversibility.IRREVERSIBLE, _BOTH),
        ActionPolicy("commitment_declined", Reversibility.IRREVERSIBLE, _BOTH),
        ActionPolicy("artifact_shared", Reversibility.IRREVERSIBLE, _BOTH),
        ActionPolicy("live_session", Reversibility.IRREVERSIBLE, _BOTH),
        ActionPolicy("consent_requested", Reversibility.IRREVERSIBLE, _BOTH),
        # Only the user can grant consent, never a model on their behalf.
        ActionPolicy(
            "consent_granted",
            Reversibility.IRREVERSIBLE,
            frozenset({Origin.USER}),
            required_assurance="eid_low",
        ),
        ActionPolicy("presence_changed", Reversibility.IDEMPOTENT, _BOTH),
        ActionPolicy(
            "value_transfer_requested",
            Reversibility.IRREVERSIBLE,
            _BOTH,
            required_assurance="eid_high",
            limits={"max_amount": "10000.00", "currencies": ["DKK", "EUR"]},
        ),
        # Emitted only by an authoritative payment provider, never proposed.
        ActionPolicy("value_transfer_confirmed", Reversibility.IRREVERSIBLE, frozenset()),
        # --- EiraSystemAPI family (Gate 1.1, ADR-0002) ---------------------
        # Shutting down or restarting loses unsaved work in open programs,
        # and even suspend cannot be taken back: irreversible, so the user
        # consents to exactly this, and the right must be granted for the
        # device (no model can grant it).
        ActionPolicy(
            "system:power.request_action",
            Reversibility.IRREVERSIBLE,
            _BOTH,
            required_assurance="eid_low",
        ),
    )
}

ASSURANCE_RANK = {"none": 0, "eid_low": 1, "idp_authenticated": 1, "org_acting": 2, "eid_high": 3}


def assurance_rank(level: str | None) -> int:
    """Unknown levels rank lowest (fail closed)."""
    return ASSURANCE_RANK.get(level or "none", 0)


def policy_for(action_type: str) -> ActionPolicy:
    policy = REGISTRY.get(action_type)
    if policy is None:
        # §6: no explicit class → irreversible; and it is not allowed at all.
        raise LayerFailure(GateCode.E_POLICY, f"no gate policy for {action_type!r}")
    if policy.reversibility is Reversibility.COMPENSABLE and not policy.compensation:
        raise LayerFailure(
            GateCode.E_POLICY, f"{action_type} is compensable without a registered compensation"
        )
    return policy


def check_limits(policy: ActionPolicy, content: dict[str, Any]) -> None:
    """Parameters must be inside the policy (layer 4)."""
    limits = policy.limits
    if "max_amount" in limits:
        amount = content["amount"]
        try:
            value = Decimal(amount["value"])
        except (InvalidOperation, KeyError, TypeError):
            raise LayerFailure(GateCode.E_POLICY, "amount is not a decimal") from None
        if value <= 0 or value > Decimal(limits["max_amount"]):
            raise LayerFailure(GateCode.E_POLICY, "amount outside policy limits")
        if amount.get("currency") not in limits["currencies"]:
            raise LayerFailure(GateCode.E_POLICY, "currency not allowed by policy")
