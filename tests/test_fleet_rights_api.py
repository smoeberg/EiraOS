"""The endpoint ↔ Fleet rights API (specs/EIRA-FLEET-RIGHTS-API-1.0.md).

Fleet is not part of these tests: a fake behind `FleetRightsClient` plays
well-behaved, offline and hostile Fleets. The OpenAPI file is checked
against the code so the published boundary cannot drift from what the
agent actually does."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import jsonschema
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.gate.policy import REGISTRY
from app.rights import agent, contract, fleet_api
from app.rights.cache import RightsCache
from app.rights.fleet_api import ApplyReport, FleetError
from tests.rights_helpers import DEVICE, TestFleet
from tests.test_gate_kernel import Clock

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = json.loads((ROOT / "specs" / "eira-fleet-rights-api-1.0.openapi.json").read_text())
SCHEMAS = OPENAPI["components"]["schemas"]


def schema(name: str) -> dict:
    return {**SCHEMAS[name], "$defs": SCHEMAS}


class FakeFleet:
    """Plays Fleet behind the interface. `signer` produces correctly signed
    sets; tests mutate `next_answer` to misbehave."""

    def __init__(self, signer: TestFleet):
        self.signer = signer
        self.reports: list[ApplyReport] = []
        self.asked: list[int | None] = []
        self.next_answer: object = None
        self.offline = False
        self.reports_fail = False

    def desired_rights(self, active_version):
        self.asked.append(active_version)
        if self.offline:
            raise FleetError("connection refused")
        if self.next_answer is not None:
            return fleet_api.parse_desired_state(self.next_answer)
        if active_version == self.signer.version:
            return fleet_api.parse_desired_state({"policy_revision": "x"})
        raw = contract.canonical(self.signer.document())
        return fleet_api.parse_desired_state({"rights_set": fleet_api.encode_rights_set(raw)})

    def report_apply(self, report):
        if self.reports_fail:
            raise FleetError("timeout")
        jsonschema.validate(report.to_json(), schema("RightsApplyResult"))
        self.reports.append(report)


@pytest.fixture
def world(tmp_path):
    clock = Clock()
    signer = TestFleet(tmp_path / "unused", clock)
    signer.version = 7
    signer.grant("obj:sag:*", principal="did:eira:anne")
    enrollment = fleet_api.Enrollment(
        DEVICE.tenant_id, DEVICE.device_id, "https://fleet.test", signer.anchors
    )
    fleet = FakeFleet(signer)
    cache = RightsCache(tmp_path / "rights")

    def sync():
        return agent.sync_once(fleet, enrollment, cache, registry=REGISTRY, wall_now=clock())

    return fleet, cache, sync, signer, clock


def test_newer_set_is_applied_and_reported(world):
    fleet, cache, sync, _, _ = world
    assert sync() == "applied"
    assert fleet.asked == [None]
    assert cache.active_meta().version == 7
    assert fleet.reports[-1].result == "applied" and fleet.reports[-1].version == 7


def test_nothing_newer_means_no_report(world):
    fleet, _, sync, _, _ = world
    sync()
    assert sync() == "unchanged"
    assert fleet.asked == [None, 7]
    assert len(fleet.reports) == 1


def test_offline_keeps_the_active_set(world):
    fleet, cache, sync, _, _ = world
    sync()
    fleet.offline = True
    assert sync() == "offline"
    assert cache.active_meta().version == 7


def test_rejected_set_reports_only_the_reason(world):
    fleet, cache, sync, signer, _ = world
    sync()
    signer.version = 3  # Fleet sends an older set
    fleet.next_answer = {"rights_set": fleet_api.encode_rights_set(contract.canonical(signer.document()))}
    assert sync() == "rejected"
    report = fleet.reports[-1]
    assert (report.reason, report.rights_set_id, report.version) == ("version_rollback", None, None)
    assert cache.active_meta().version == 7


def test_set_from_another_tenants_key_is_rejected(world, tmp_path):
    fleet, cache, sync, _, clock = world
    other = TestFleet(tmp_path / "x", clock)
    other._key = Ed25519PrivateKey.generate()  # same key_id, another key
    other.version = 9
    fleet.next_answer = {"rights_set": fleet_api.encode_rights_set(contract.canonical(other.document()))}
    assert sync() == "rejected"
    assert fleet.reports[-1].reason == "bad_signature"
    assert cache.active_meta() is None


def test_unreported_result_is_not_fatal(world):
    fleet, cache, sync, _, _ = world
    fleet.reports_fail = True
    assert sync() == "applied"
    assert cache.active_meta().version == 7


@pytest.mark.parametrize(
    "answer",
    [
        [],  # not an object
        {"rights_set": 42},
        {"rights_set": "not base64!"},
        {"rights_set": {"eira_rights": "1"}},  # embedded JSON: forbidden by the API
    ],
)
def test_protocol_violations_never_reach_the_cache(world, answer):
    fleet, cache, sync, _, _ = world
    fleet.next_answer = answer
    assert sync() == "offline"  # ProtocolViolation is a FleetError
    assert cache.active_meta() is None


def test_bytes_are_verified_exactly_as_sent(world):
    """A set re-serialised by a JSON layer still verifies (the signature is
    over the canonical form), but duplicate keys smuggled in are refused."""
    fleet, cache, sync, signer, _ = world
    raw = contract.canonical(signer.document()).decode()
    smuggled = raw.replace('"eira_rights":"1"', '"eira_rights":"1","eira_rights":"1"', 1)
    fleet.next_answer = {"rights_set": fleet_api.encode_rights_set(smuggled.encode())}
    assert sync() == "rejected"
    assert fleet.reports[-1].reason == "malformed"


def test_heartbeat_fields_match_the_published_schema(world):
    _, cache, sync, _, clock = world
    missing = agent.heartbeat_fields(cache, clock())
    jsonschema.validate(missing.to_json(), schema("RightsHeartbeat"))
    assert missing.rights_state == "missing"
    sync()
    active = agent.heartbeat_fields(cache, clock())
    jsonschema.validate(active.to_json(), schema("RightsHeartbeat"))
    assert (active.rights_state, active.rights_version) == ("active", 7)
    clock.now += timedelta(days=30)
    assert agent.heartbeat_fields(cache, clock()).rights_state == "expired"


# --- the published file and the code agree ------------------------------------


def test_openapi_reasons_are_exactly_the_contracts():
    published = set(SCHEMAS["RightsApplyResult"]["properties"]["reason"]["enum"]) - {None}
    reasons = {v for k, v in vars(contract.Reason).items() if not k.startswith("_")}
    assert published == reasons


def test_openapi_is_a_valid_document():
    from jsonschema import Draft202012Validator

    for name in ("DesiredState", "RightsApplyResult", "RightsHeartbeat", "Enrollment"):
        Draft202012Validator.check_schema(SCHEMAS[name])
    assert set(OPENAPI["paths"]) == {"/v1/desired-state", "/v1/report/apply-result", "/v1/heartbeat"}


def test_newer_example_is_a_real_vector():
    ref = OPENAPI["components"]["examples"]["DesiredStateNewer"]["externalValue"]
    vector = json.loads((ROOT / "specs" / ref).resolve().read_text())
    encoded = fleet_api.encode_rights_set(vector["raw"].encode())
    jsonschema.validate({"rights_set": encoded}, schema("DesiredState"))
    assert fleet_api.parse_desired_state({"rights_set": encoded}).rights_set == vector["raw"].encode()


def test_enrollment_schema_and_parser_agree(tmp_path):
    good = {
        "eira_enrollment": "1", "tenant_id": "kk", "device_id": "dev-1",
        "fleet_url": "https://fleet.kk.example",
        "rights_anchors": {"kk-1": {"kind": "managed", "public_key": "A" * 43}},
    }
    jsonschema.validate(good, schema("Enrollment"))
    assert fleet_api.parse_enrollment(good).device == contract.Device(True, "kk", "dev-1")
    for bad in (
        {**good, "fleet_url": "http://fleet.kk.example"},
        {**good, "rights_anchors": {}},
        {**good, "rights_anchors": {"k": {"kind": "default", "public_key": "A" * 43}}},
        {k: v for k, v in good.items() if k != "rights_anchors"},
    ):
        with pytest.raises(ValueError):
            fleet_api.parse_enrollment(bad)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema("Enrollment"))
    path = tmp_path / "enrollment.json"
    assert fleet_api.read_enrollment(path) is None
    path.write_text("{}")
    with pytest.raises(ValueError):
        fleet_api.read_enrollment(path)


def test_agent_reaches_fleet_with_an_expired_set(world):
    """RIGHTS-SET §5.1 / §8 item 5: contact with Fleet never depends on the set."""
    fleet, cache, sync, signer, clock = world
    sync()
    clock.now += timedelta(days=30)
    assert agent.heartbeat_fields(cache, clock()).rights_state == "expired"
    signer.version = 8
    assert sync() == "applied"
    assert cache.active_meta().version == 8
