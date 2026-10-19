"""Versioned CEL policy storage for administrative transformations."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.core.constraint import Constraint


@dataclass(frozen=True)
class PolicyDefinition:
    transformation_type: str
    rule_id: str
    expression: str
    error_message: str
    metadata: dict[str, Any] = field(default_factory=dict)


DEFAULT_POLICIES = (
    PolicyDefinition(
        "approve_payment",
        "payment_amount_limit",
        "candidate.payload.amount <= 100000",
        "Beløbet overstiger den administrative grænse på 100.000 kr.",
    ),
    PolicyDefinition(
        "approve_payment",
        "payment_org_assurance",
        "world.actor.assurance_level == 'org_acting'",
        "Udbetalingen kræver MitID Erhverv step-up.",
        {"required_assurance": "org_acting", "step_up_method": "mitid_erhverv"},
    ),
    PolicyDefinition(
        "approve_grant",
        "grant_amount_limit",
        "candidate.payload.amount <= 100000",
        "Bevillingen overstiger den administrative grænse på 100.000 kr.",
    ),
    PolicyDefinition(
        "approve_grant",
        "grant_org_assurance",
        "world.actor.assurance_level == 'org_acting'",
        "Bevillingen kræver MitID Erhverv step-up.",
        {"required_assurance": "org_acting", "step_up_method": "mitid_erhverv"},
    ),
    PolicyDefinition(
        "create_building_permit",
        "permit_org_assurance",
        "world.actor.assurance_level == 'org_acting'",
        "Oprettelse af byggetilladelse kræver MitID Erhverv step-up.",
        {"required_assurance": "org_acting", "step_up_method": "mitid_erhverv"},
    ),
    PolicyDefinition(
        "submit_case",
        "case_due_date",
        "candidate.payload.due_date >= world.now",
        "Sagens frist må ikke ligge i fortiden.",
    ),
    PolicyDefinition(
        "award_case",
        "case_impartiality",
        "candidate.payload.beneficiary_actor_id != world.actor.id",
        "Aktøren er inhabil i denne sag.",
    ),
)


class PolicyStore:
    def __init__(
        self,
        db_path: str = ":memory:",
        *,
        seed_defaults: bool = True,
    ) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS policy_rules (
                transformation_type TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                expression TEXT NOT NULL,
                error_message TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (transformation_type, rule_id, version)
            )
            """
        )
        columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(policy_rules)")
        }
        if "content_hash" not in columns:
            self._connection.execute(
                "ALTER TABLE policy_rules ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''"
            )
            rows = self._connection.execute("SELECT * FROM policy_rules").fetchall()
            for row in rows:
                digest = self._rule_digest(
                    row["transformation_type"], row["rule_id"], row["version"],
                    row["expression"], row["error_message"], row["metadata_json"],
                    bool(row["enabled"]),
                )
                self._connection.execute(
                    "UPDATE policy_rules SET content_hash = ? WHERE transformation_type = ? AND rule_id = ? AND version = ?",
                    (digest, row["transformation_type"], row["rule_id"], row["version"]),
                )
        self._connection.execute(
            "CREATE TRIGGER IF NOT EXISTS policy_rules_immutable_update "
            "BEFORE UPDATE ON policy_rules BEGIN "
            "SELECT RAISE(ABORT, 'policy rules are immutable'); END"
        )
        self._connection.execute(
            "CREATE TRIGGER IF NOT EXISTS policy_rules_immutable_delete "
            "BEFORE DELETE ON policy_rules BEGIN "
            "SELECT RAISE(ABORT, 'policy rules are immutable'); END"
        )
        self._connection.commit()
        if seed_defaults:
            self.seed(DEFAULT_POLICIES)

    @staticmethod
    def _rule_digest(
        transformation_type: str,
        rule_id: str,
        version: int,
        expression: str,
        error_message: str,
        metadata_json: str,
        enabled: bool,
    ) -> str:
        canonical = json.dumps(
            {
                "transformation_type": transformation_type,
                "rule_id": rule_id,
                "version": version,
                "expression": expression,
                "error_message": error_message,
                "metadata": json.loads(metadata_json),
                "enabled": enabled,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha3_256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def _verify_row(cls, row: sqlite3.Row) -> None:
        expected = cls._rule_digest(
            row["transformation_type"], row["rule_id"], row["version"],
            row["expression"], row["error_message"], row["metadata_json"],
            bool(row["enabled"]),
        )
        if not row["content_hash"] or row["content_hash"] != expected:
            raise ValueError("policy_rule_integrity_check_failed")

    def close(self) -> None:
        self._connection.close()

    def seed(self, definitions: Iterable[PolicyDefinition]) -> None:
        for definition in definitions:
            with self._lock:
                exists = self._connection.execute(
                    """
                    SELECT 1 FROM policy_rules
                    WHERE transformation_type = ? AND rule_id = ?
                    LIMIT 1
                    """,
                    (definition.transformation_type, definition.rule_id),
                ).fetchone()
            if not exists:
                self.add_rule(
                    definition.transformation_type,
                    definition.rule_id,
                    definition.expression,
                    definition.error_message,
                    metadata=definition.metadata,
                )

    def add_rule(
        self,
        transformation_type: str,
        rule_id: str,
        expression: str,
        error_message: str,
        *,
        metadata: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> Constraint:
        if not transformation_type or not rule_id:
            raise ValueError("transformation_type and rule_id are required")
        with self._lock:
            row = self._connection.execute(
                """
                SELECT COALESCE(MAX(version), 0) AS version
                FROM policy_rules
                WHERE transformation_type = ? AND rule_id = ?
                """,
                (transformation_type, rule_id),
            ).fetchone()
            version = int(row["version"]) + 1
            self._connection.execute(
                """
                SELECT 1
                FROM policy_rules
                WHERE transformation_type = ? AND rule_id = ?
                LIMIT 1
                """,
                (transformation_type, rule_id),
            )
            metadata_json = json.dumps(metadata or {}, sort_keys=True)
            digest = self._rule_digest(
                transformation_type, rule_id, version, expression,
                error_message, metadata_json, enabled,
            )
            self._connection.execute(
                """
                INSERT INTO policy_rules
                (transformation_type, rule_id, version, expression,
                 error_message, metadata_json, enabled, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transformation_type,
                    rule_id,
                    version,
                    expression,
                    error_message,
                    metadata_json,
                    int(enabled),
                    digest,
                ),
            )
            self._connection.commit()
        return Constraint(
            id=rule_id,
            transformation_type=transformation_type,
            version=version,
            expression=expression,
            error_message=error_message,
            metadata=metadata or {},
            enabled=enabled,
        )

    update_rule = add_rule

    def get_constraints(
        self, transformation_type: str, *, include_disabled: bool = False
    ) -> list[Constraint]:
        query = """
            SELECT current.*
            FROM policy_rules AS current
            JOIN (
                SELECT transformation_type, rule_id, MAX(version) AS max_version
                FROM policy_rules
                WHERE transformation_type IN (?, '*')
                GROUP BY transformation_type, rule_id
            ) AS latest
              ON latest.transformation_type = current.transformation_type
             AND latest.rule_id = current.rule_id
             AND latest.max_version = current.version
            ORDER BY current.transformation_type, current.rule_id
        """
        with self._lock:
            rows = self._connection.execute(query, (transformation_type,)).fetchall()
        constraints = []
        for row in rows:
            self._verify_row(row)
            if not include_disabled and not row["enabled"]:
                continue
            constraints.append(
                Constraint(
                    id=row["rule_id"],
                    transformation_type=row["transformation_type"],
                    version=row["version"],
                    expression=row["expression"],
                    error_message=row["error_message"],
                    metadata=json.loads(row["metadata_json"]),
                    enabled=bool(row["enabled"]),
                )
            )
        return constraints

    def get_rule_history(
        self, transformation_type: str, rule_id: str
    ) -> list[Constraint]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM policy_rules
                WHERE transformation_type = ? AND rule_id = ?
                ORDER BY version ASC
                """,
                (transformation_type, rule_id),
            ).fetchall()
        for row in rows:
            self._verify_row(row)
        return [
            Constraint(
                id=row["rule_id"],
                transformation_type=row["transformation_type"],
                version=row["version"],
                expression=row["expression"],
                error_message=row["error_message"],
                metadata=json.loads(row["metadata_json"]),
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]
