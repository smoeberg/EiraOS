from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.database import get_connection
from app.ipc.client import IpcClient

MAX_DELEGATION = timedelta(days=30)


class DelegationScope(BaseModel):
    actions: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=lambda: ["*"])
    conditions: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(frozen=True, extra="forbid")


class DelegationCreateRequest(BaseModel):
    delegee_id: str
    scope: DelegationScope
    expires_in: timedelta = timedelta(hours=24)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DelegationRevokeRequest(BaseModel):
    delegation_id: str


class DelegationCheckRequest(BaseModel):
    delegee_id: str
    action: str
    target: str


@dataclass(frozen=True)
class Delegation:
    id: str
    delegator_id: str
    delegee_id: str
    scope: DelegationScope
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None
    metadata: dict[str, Any]

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > datetime.now(timezone.utc)

    def can_perform(self, action: str, target: str) -> bool:
        if not self.is_active:
            return False
        if "*" not in self.scope.actions and action not in self.scope.actions:
            return False
        if "*" not in self.scope.targets:
            if not any(
                target == pattern
                or (pattern.endswith("*") and target.startswith(pattern[:-1]))
                for pattern in self.scope.targets
            ):
                return False
        return _conditions_allow(self.scope.conditions, target)


def _conditions_allow(conditions: dict[str, Any], target: str) -> bool:
    if not conditions:
        return True
    allowed_targets = conditions.get("allowed_targets")
    if allowed_targets is not None:
        if not isinstance(allowed_targets, list) or target not in allowed_targets:
            return False
    return True


class DelegationRepository:
    def _ensure_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS delegations (
                    id TEXT PRIMARY KEY,
                    delegator_id TEXT NOT NULL,
                    delegee_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_delegations_active "
                "ON delegations(delegee_id, expires_at, revoked_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_delegations_delegator "
                "ON delegations(delegator_id)"
            )

    @staticmethod
    def _row(row: Any) -> Delegation:
        return Delegation(
            id=row["id"],
            delegator_id=row["delegator_id"],
            delegee_id=row["delegee_id"],
            scope=DelegationScope.model_validate_json(row["scope"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            revoked_at=datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None,
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def create(self, delegator_id: str, delegee_id: str, scope: DelegationScope,
               expires_at: datetime, metadata: dict[str, Any]) -> Delegation:
        self._ensure_schema()
        now = datetime.now(timezone.utc)
        delegation_id = str(uuid.uuid4())
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO delegations
                    (id, delegator_id, delegee_id, scope, expires_at, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (delegation_id, delegator_id, delegee_id, scope.model_dump_json(),
                 expires_at.isoformat(), now.isoformat(), json.dumps(metadata, sort_keys=True)),
            )
        return Delegation(delegation_id, delegator_id, delegee_id, scope,
                          expires_at, now, None, dict(metadata))

    def get_by_id(self, delegation_id: str) -> Delegation | None:
        self._ensure_schema()
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM delegations WHERE id = ?", (delegation_id,)).fetchone()
        return self._row(row) if row else None

    def active_for_delegee(self, delegee_id: str) -> list[Delegation]:
        self._ensure_schema()
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM delegations
                   WHERE delegee_id = ? AND revoked_at IS NULL AND expires_at > ?
                   ORDER BY expires_at""",
                (delegee_id, now),
            ).fetchall()
        return [self._row(row) for row in rows]

    def active_for_delegator(self, delegator_id: str) -> list[Delegation]:
        self._ensure_schema()
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM delegations
                   WHERE delegator_id = ? AND revoked_at IS NULL AND expires_at > ?
                   ORDER BY expires_at""",
                (delegator_id, now),
            ).fetchall()
        return [self._row(row) for row in rows]

    def revoke(self, delegation_id: str) -> bool:
        self._ensure_schema()
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            result = conn.execute(
                "UPDATE delegations SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (now, delegation_id),
            )
        return result.rowcount == 1

    def delete(self, delegation_id: str) -> None:
        self._ensure_schema()
        with get_connection() as conn:
            conn.execute("DELETE FROM delegations WHERE id = ?", (delegation_id,))


class DelegationService:
    def __init__(self, repo: DelegationRepository | None = None) -> None:
        self.repo = repo or DelegationRepository()

    def create_delegation(self, delegator_id: str, request: DelegationCreateRequest) -> Delegation:
        if not delegator_id:
            raise PermissionError("delegator identity is required")
        if not request.delegee_id.startswith("model:"):
            raise PermissionError("only model delegatees are supported")
        if not request.scope.actions:
            raise ValueError("delegation must contain at least one action")
        if {"execute", "decide", "admin"}.intersection(request.scope.actions):
            raise PermissionError("delegation cannot grant execute, decide or admin")
        if request.expires_in <= timedelta(0) or request.expires_in > MAX_DELEGATION:
            raise ValueError("delegation expiry must be > 0 and <= 30 days")

        delegation = self.repo.create(
            delegator_id, request.delegee_id, request.scope,
            datetime.now(timezone.utc) + request.expires_in, request.metadata,
        )
        try:
            self._audit("delegation.created", delegator_id, {
                "delegation_id": delegation.id,
                "delegee_id": delegation.delegee_id,
                "scope": delegation.scope.model_dump(),
                "expires_at": delegation.expires_at.isoformat(),
            })
        except Exception:
            self.repo.delete(delegation.id)
            raise
        return delegation

    def revoke_delegation(self, request: DelegationRevokeRequest, revoked_by: str) -> bool:
        delegation = self.repo.get_by_id(request.delegation_id)
        if delegation is None:
            raise ValueError("delegation not found")
        if delegation.delegator_id != revoked_by:
            raise PermissionError("only the delegator can revoke this delegation")
        success = self.repo.revoke(request.delegation_id)
        if success:
            self._audit("delegation.revoked", revoked_by, {
                "delegation_id": delegation.id,
                "delegee_id": delegation.delegee_id,
            })
        return success

    def check_delegation(self, request: DelegationCheckRequest) -> bool:
        return any(
            delegation.can_perform(request.action, request.target)
            for delegation in self.repo.active_for_delegee(request.delegee_id)
        )

    def delegation_for(self, delegee_id: str, action: str, target: str) -> Delegation | None:
        for delegation in self.repo.active_for_delegee(delegee_id):
            if delegation.can_perform(action, target):
                return delegation
        return None

    @staticmethod
    def _audit(event_type: str, actor_id: str, details: dict[str, Any]) -> None:
        result = IpcClient("stated").call(
            "audit.append", {"event_type": event_type, "actor_id": actor_id, "details": details}
        )
        if not isinstance(result, dict) or result.get("status") != "appended":
            raise RuntimeError("delegation audit append failed")
