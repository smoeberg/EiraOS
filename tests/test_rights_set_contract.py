"""EIRA Rights Set 1.0 — the shared vectors are the contract.

eira-fleet-control pins this repo and runs the same vector files against its
issuer. If this test and that one disagree, the two sides have drifted.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.gate.policy import REGISTRY
from app.rights import contract

VECTORS = Path(__file__).parent / "vectors" / "rights-set"
CONTEXT = json.loads((VECTORS / "_context.json").read_text(encoding="utf-8"))
APPLY = sorted(VECTORS.glob("apply-*.json"))


def _ts(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _anchors() -> dict[str, contract.Anchor]:
    out = {}
    for key_id, anchor in CONTEXT["anchors"].items():
        raw = base64.urlsafe_b64decode(anchor["public_key"] + "=" * (-len(anchor["public_key"]) % 4))
        out[key_id] = contract.Anchor(kind=anchor["kind"], public_key=raw)
    return out


def _registry() -> list[str]:
    # Vector keys are written as action keys; turn them back into gate names.
    return [k if k.startswith("system:") else k[len("edp:"):] for k in CONTEXT["registry"]]


def test_vector_context_matches_contract_constants():
    assert CONTEXT["domain"] == contract.DOMAIN.decode()
    assert CONTEXT["max_ttl_seconds"] == int(contract.MAX_TTL.total_seconds())
    assert "TEST KEYS" in CONTEXT["note"]


def test_every_required_vector_exists():
    names = {p.stem.removeprefix("apply-") for p in APPLY}
    required = {
        "expired", "version-rollback", "wrong-device", "wrong-tenant", "wrong-domain-prefix",
        "missing-template", "ttl-over-cap", "unknown-key-id", "unknown-action", "wildcard-action",
        "unknown-field", "float-version", "duplicate-key", "same-version-same-content",
        "same-version-other-content", "default-on-enrolled", "tampered-after-signing",
    }
    assert required <= names, required - names


@pytest.mark.parametrize("path", APPLY, ids=lambda p: p.stem)
def test_apply_vector(path: Path):
    vector = json.loads(path.read_text(encoding="utf-8"))
    device = contract.Device(**vector["device"])
    active = contract.Active(**vector["active"]) if vector["active"] else None
    verdict = contract.verify(
        vector["raw"].encode("utf-8"),
        anchors=_anchors(),
        device=device,
        active=active,
        now=_ts(vector["now"]),
        registry=_registry(),
        max_ttl=timedelta(seconds=CONTEXT["max_ttl_seconds"]),
    )
    expect = vector["expect"]
    assert verdict.ok is expect["ok"], (vector["name"], verdict.reason)
    assert verdict.reason == expect.get("reason")
    assert verdict.noop is expect.get("noop", False)


def test_authorize_vectors():
    data = json.loads((VECTORS / "authorize.json").read_text(encoding="utf-8"))
    for query in data["queries"]:
        decision = contract.authorize(
            data["rights_set"],
            principal=query["principal"],
            groups=query["groups"],
            scope=query["scope"],
            action=query["action"],
            now=_ts(query["now"]),
        )
        expect = query["expect"]
        assert decision.allowed is expect["allowed"], query["name"]
        assert decision.reason == expect["reason"], query["name"]
        assert decision.grant_index == expect.get("grant_index"), query["name"]
        assert decision.required_assurance == expect.get("required_assurance"), query["name"]


def test_vector_registry_keys_exist_in_the_gate():
    """The vectors must not test against actions the gate does not have."""
    assert set(CONTEXT["registry"]) <= contract.action_keys(REGISTRY)


def test_assurance_can_only_be_raised():
    assert contract.stricter_assurance("eid_low", "eid_high") == "eid_high"
    assert contract.stricter_assurance("eid_high", "eid_low") == "eid_high"
    assert contract.stricter_assurance("none", None) == "none"


def test_valid_vector_fails_once_any_signed_byte_changes():
    vector = json.loads((VECTORS / "apply-valid-managed.json").read_text(encoding="utf-8"))
    raw = vector["raw"].replace('"version":42', '"version":43')
    verdict = contract.verify(
        raw.encode(), anchors=_anchors(), device=contract.Device(**vector["device"]),
        active=None, now=_ts(vector["now"]), registry=_registry(),
    )
    assert verdict.reason == "bad_signature"


def test_oversized_set_is_malformed():
    verdict = contract.verify(
        b" " * (contract.MAX_BYTES + 1), anchors=_anchors(),
        device=contract.Device(enrolled=False), active=None,
        now=_ts("2026-11-07T12:00:00Z"), registry=_registry(),
    )
    assert verdict.reason == "malformed"
