from __future__ import annotations

import sqlite3

import pytest

from app.core.policy_store import PolicyDefinition, PolicyStore


def test_policy_seed_is_idempotent_and_rule_updates_create_immutable_history():
    policies = PolicyStore(seed_defaults=False)
    original = PolicyDefinition(
        "approve_payment", "amount_limit", "candidate.payload.amount <= 100000",
        "Beløbet er for højt.", {"limit": 100000},
    )
    policies.seed([original])
    policies.seed([
        PolicyDefinition(
            "approve_payment", "amount_limit", "candidate.payload.amount <= 1",
            "Forsøg på at ændre den seedede regel.",
        )
    ])

    history = policies.get_rule_history("approve_payment", "amount_limit")
    assert len(history) == 1
    assert history[0].expression == original.expression
    row = policies._connection.execute(
        "SELECT content_hash FROM policy_rules WHERE transformation_type = ? AND rule_id = ? AND version = 1",
        ("approve_payment", "amount_limit"),
    ).fetchone()
    assert len(row["content_hash"]) == 64

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        policies._connection.execute(
            "UPDATE policy_rules SET expression = ? WHERE transformation_type = ? AND rule_id = ? AND version = 1",
            ("true", "approve_payment", "amount_limit"),
        )

    policies.add_rule(
        "approve_payment", "amount_limit", "candidate.payload.amount <= 1",
        "Ny version med ændret grænse.",
    )
    history = policies.get_rule_history("approve_payment", "amount_limit")
    assert [rule.version for rule in history] == [1, 2]
    assert history[0].expression == original.expression
    assert history[1].expression == "candidate.payload.amount <= 1"
    hashes = policies._connection.execute(
        "SELECT content_hash FROM policy_rules WHERE transformation_type = ? AND rule_id = ? ORDER BY version",
        ("approve_payment", "amount_limit"),
    ).fetchall()
    assert hashes[0]["content_hash"] != hashes[1]["content_hash"]


def test_policy_store_detects_rule_hash_tampering():
    policies = PolicyStore(seed_defaults=False)
    policies.add_rule(
        "approve_payment", "amount_limit", "candidate.payload.amount <= 100000",
        "Beløbet er for højt.",
    )
    policies._connection.execute("DROP TRIGGER policy_rules_immutable_update")
    policies._connection.execute(
        "UPDATE policy_rules SET expression = ? WHERE transformation_type = ? AND rule_id = ?",
        ("true", "approve_payment", "amount_limit"),
    )

    with pytest.raises(ValueError, match="policy_rule_integrity_check_failed"):
        policies.get_constraints("approve_payment")


