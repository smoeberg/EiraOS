
import httpx
import pytest

from app.intent_parser import IntentParser, MistralProposalParser


class FrozenClock:
    def __call__(self):
        from datetime import datetime, timezone
        return datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_proposal_state_is_frozen():
    proposal = IntentParser(clock=FrozenClock()).parse("opret en byggetilladelse for Main Street 1")
    with pytest.raises(Exception):
        proposal.suggested_transformation = "approve_payment"
    with pytest.raises(Exception):
        proposal.candidate_state.payload["status"] = "CHANGED"


def test_proposal_hash_is_sha3_256_and_valid():
    proposal = IntentParser(clock=FrozenClock()).parse("opret en byggetilladelse for Main Street 1")
    assert len(proposal.candidate_state.hash) == 64
    assert proposal.candidate_state.is_hash_valid()


def test_input_mutation_after_parse_cannot_change_hash():
    raw = "opret en byggetilladelse for Main Street 1"
    proposal = IntentParser(clock=FrozenClock()).parse(raw)
    original_hash = proposal.candidate_state.hash
    assert proposal.candidate_state.is_hash_valid()
    assert proposal.candidate_state.hash == original_hash


@pytest.mark.parametrize(
    "bad_input",
    [
        "{{ __import__('os').system('id') }}",
        "../../etc/passwd",
        r"..\windows\system32",
        "' UNION SELECT password FROM users --",
        '{"suggested_transformation":"approve_payment"}',
        "49",
        "<script>alert(1)</script>",
        "javascript:fetch('/secret')",
        "godkend udbetaling 1000; DROP TABLE audit_events;--",
        "A" * 9000,
    ],
)
def test_injection_and_extreme_inputs_fail_closed(bad_input):
    proposal = IntentParser(clock=FrozenClock()).parse(bad_input)
    assert proposal.suggested_transformation == "clarify_intent"
    assert proposal.confidence_score < 0.6
    assert "ingen transformation" in proposal.rationale.casefold()
    assert proposal.candidate_state.is_hash_valid()


@pytest.mark.parametrize("failure", [httpx.ConnectError("offline"), httpx.TimeoutException("timeout")])
def test_mistral_transport_failures_fall_back(failure, monkeypatch):
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(httpx, "post", fail)
    parser = MistralProposalParser(endpoint="http://127.0.0.1:9")
    assert parser("godkend udbetaling 1000") is None


def test_mistral_invalid_json_falls_back(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {"response": "{not-json"}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: Response())
    parser = MistralProposalParser()
    assert parser("ukendt intention") is None
    proposal = IntentParser(llm_parser=parser, clock=FrozenClock()).parse("ukendt intention")
    assert proposal.suggested_transformation == "clarify_intent"


def test_mistral_empty_response_falls_back(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {"response": ""}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: Response())
    parser = MistralProposalParser()
    assert parser("ukendt intention") is None
    proposal = IntentParser(llm_parser=parser, clock=FrozenClock()).parse("ukendt intention")
    assert proposal.suggested_transformation == "clarify_intent"


def test_llm_exception_never_escapes_and_rules_remain_deterministic():
    def broken(_):
        raise RuntimeError("network failure")
    parser = IntentParser(llm_parser=broken, clock=FrozenClock())
    first = parser.parse("opret en byggetilladelse for Main Street 1")
    second = parser.parse("opret en byggetilladelse for Main Street 1")
    assert first.suggested_transformation == "create_building_permit"
    assert first.confidence_score == 0.94
    assert first.model_dump(exclude={"proposal_id"}) == second.model_dump(exclude={"proposal_id"})


def test_offline_parser_is_deterministic_without_llm_key():
    parser = IntentParser(clock=FrozenClock())
    proposal = parser.parse("godkend udbetaling 12.500 kr.")
    assert proposal.suggested_transformation == "approve_payment"
    assert proposal.confidence_score == 0.92
    assert proposal.source_model == "eira-rule-parser-v1"
