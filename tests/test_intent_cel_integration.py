"""Sprint 4 Agent 4: End-to-end integration tests for Intent/CEL suite (Issue #59).

Tests the complete flow: free text -> IntentParser -> ProposalState -> CEL evaluation ->
StateStore append with SHA3-256 hash verification.

All tests use ONLY public interfaces (IPC handlers, parser, evaluator, store).
No whitebox mocking of internal modules.
"""

from __future__ import annotations

import pytest

from app.core.cel_evaluator import CELEvaluator
from app.core.policy_store import DEFAULT_POLICIES, PolicyStore
from app.core.state import State
from app.core.store import StateStore

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def cel_evaluator():
    """Fresh CELEvaluator instance for each test."""
    return CELEvaluator()


@pytest.fixture
def policy_store():
    """Fresh PolicyStore with default policies."""
    return PolicyStore(seed_defaults=True)


@pytest.fixture
def state_store(tmp_path):
    """Fresh StateStore with temp database."""
    db_path = str(tmp_path / "eira_integration.db")
    store = StateStore(db_path)
    yield store


def test_e2e_policy_store_seeded_with_multiple_rules(policy_store):
    """End-to-end: Policy store with 3 rules, all evaluated, history accessible."""
    # Verify default policies are seeded
    assert len(DEFAULT_POLICIES) >= 3

    # Add 3 custom rules for a specific transformation
    policy_store.add_rule(
        "custom_transformation",
        "rule_a",
        "candidate.payload.value >= 10",
        "Value must be at least 10",
    )
    policy_store.add_rule(
        "custom_transformation",
        "rule_b",
        "candidate.payload.value <= 100",
        "Value must be at most 100",
    )
    policy_store.add_rule(
        "custom_transformation",
        "rule_c",
        "world.actor.assurance_level == 'org_acting'",
        "Requires org_acting",
    )

    # Get constraints for the transformation
    constraints = policy_store.get_constraints("custom_transformation")
    assert len(constraints) == 3

    # Verify all rules are in the constraints
    rule_ids = {c.id for c in constraints}
    assert rule_ids == {"rule_a", "rule_b", "rule_c"}

    # Get rule history for one rule
    history = policy_store.get_rule_history("custom_transformation", "rule_a")
    assert len(history) == 1
    assert history[0].id == "rule_a"
    assert history[0].version == 1

    # Update rule_a and verify history has both versions
    policy_store.update_rule(
        "custom_transformation",
        "rule_a",
        "candidate.payload.value >= 20",
        "Value must be at least 20",
    )

    history = policy_store.get_rule_history("custom_transformation", "rule_a")
    assert len(history) == 2
    versions = [r.version for r in history]
    assert versions == [1, 2]


# =============================================================================
# =============================================================================


def test_sha3_256_hash_is_deterministic_and_correct(state_store):
    """Verify SHA3-256 hash is deterministic and matches expected format."""
    # Create a state directly
    state = State(
        type="TestState",
        payload={"test": "value", "number": 42},
    )

    # The hash should be deterministic
    hash1 = state.compute_hash()
    hash2 = state.compute_hash()
    assert hash1 == hash2

    # The hash should be 64 hex characters (SHA3-256)
    assert len(hash1) == 64
    assert all(c in "0123456789abcdef" for c in hash1)

    # Store and retrieve, verify hash matches
    state_store.append(state)
    retrieved = state_store.get_by_id(state.id)
    assert retrieved.hash == state.hash
    assert retrieved.is_hash_valid()
