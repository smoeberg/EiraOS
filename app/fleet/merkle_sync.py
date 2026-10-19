from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.core.state import State

_EMPTY_ROOT = hashlib.sha3_256(b"eira-merkle-dag-v1\x00").hexdigest()
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class StateHeader:
    """Minimal immutable metadata needed to compare DAG ancestry."""

    id: str
    version: int
    hash: str
    previous_state_id: str | None
    timestamp_ns: int = 0

    @classmethod
    def from_value(cls, value: State | Mapping[str, Any]) -> StateHeader:
        if isinstance(value, State):
            return cls(
                id=str(value.id),
                version=value.version,
                hash=value.hash,
                previous_state_id=(
                    str(value.previous_state_id) if value.previous_state_id else None
                ),
                timestamp_ns=value.timestamp_ns,
            )
        state_id = value.get("id")
        state_hash = value.get("hash")
        previous = value.get("previous_state_id")
        if state_id is None or state_hash is None:
            raise ValueError("state_header_missing_id_or_hash")
        return cls(
            id=str(state_id),
            version=int(value.get("version", 1)),
            hash=str(state_hash),
            previous_state_id=str(previous) if previous is not None else None,
            timestamp_ns=int(value.get("timestamp_ns", 0)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "hash": self.hash,
            "previous_state_id": self.previous_state_id,
            "timestamp_ns": self.timestamp_ns,
        }


@dataclass(frozen=True)
class MerkleSnapshot:
    root: str
    headers: tuple[StateHeader, ...]
    heads: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "heads": list(self.heads),
            "headers": [header.as_dict() for header in self.headers],
        }


@dataclass(frozen=True)
class SyncDiff:
    local_root: str
    remote_root: str
    missing_from_local: tuple[str, ...]
    missing_from_remote: tuple[str, ...]

    @property
    def in_sync(self) -> bool:
        return self.local_root == self.remote_root


@dataclass(frozen=True)
class ForkResolution:
    """A sync proposal; conflicts are surfaced, never silently canonicalized."""

    snapshot: MerkleSnapshot
    canonical_head: str | None
    conflicting_ids: tuple[str, ...]

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicting_ids)


class MerkleSyncEngine:
    """Build deterministic Merkle commitments and hash-only sync diffs for State DAGs."""

    @staticmethod
    def _headers(
        values: Iterable[State | Mapping[str, Any] | StateHeader],
    ) -> tuple[StateHeader, ...]:
        by_hash: dict[str, StateHeader] = {}
        by_id: dict[str, StateHeader] = {}
        for value in values:
            if isinstance(value, State) and not value.is_hash_valid():
                raise ValueError("state_hash_verification_failed")
            header = value if isinstance(value, StateHeader) else StateHeader.from_value(value)
            if not header.id or not _HASH_RE.fullmatch(header.hash):
                raise ValueError("invalid_state_header")
            if header.version < 1 or header.timestamp_ns < 0:
                raise ValueError("invalid_state_metadata")
            same_hash = by_hash.get(header.hash)
            if same_hash is not None and same_hash != header:
                raise ValueError("conflicting_metadata_for_state_hash")
            same_id = by_id.get(header.id)
            if same_id is not None and same_id.hash != header.hash:
                raise ValueError(f"conflicting_immutable_state_id:{header.id}")
            by_hash[header.hash] = header
            by_id[header.id] = header
        return tuple(sorted(by_hash.values(), key=lambda item: (item.timestamp_ns, item.id, item.hash)))

    @staticmethod
    def _node_commitment(
        header: StateHeader,
        by_id: Mapping[str, StateHeader],
        cache: dict[str, str],
        active: set[str],
    ) -> str:
        if header.hash in cache:
            return cache[header.hash]
        if header.id in active:
            raise ValueError("state_dag_cycle_detected")
        active.add(header.id)
        if header.previous_state_id is None:
            parent = "root"
        elif header.previous_state_id not in by_id:
            parent = f"missing:{header.previous_state_id}"
        else:
            parent = MerkleSyncEngine._node_commitment(
                by_id[header.previous_state_id], by_id, cache, active
            )
        active.remove(header.id)
        material = json.dumps(
            {"hash": header.hash, "parent": parent},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        commitment = hashlib.sha3_256(b"eira-merkle-node-v1\x00" + material).hexdigest()
        cache[header.hash] = commitment
        return commitment

    def snapshot(
        self, values: Iterable[State | Mapping[str, Any] | StateHeader]
    ) -> MerkleSnapshot:
        headers = self._headers(values)
        if not headers:
            return MerkleSnapshot(_EMPTY_ROOT, (), ())
        by_id = {header.id: header for header in headers}
        # Validate every component, including disconnected cycles with no DAG heads.
        completed: set[str] = set()
        for start_id in by_id:
            path: set[str] = set()
            current_id: str | None = start_id
            while current_id is not None and current_id in by_id:
                if current_id in completed:
                    break
                if current_id in path:
                    raise ValueError("state_dag_cycle_detected")
                path.add(current_id)
                current_id = by_id[current_id].previous_state_id
            completed.update(path)
        referenced = {
            header.previous_state_id
            for header in headers
            if header.previous_state_id is not None
        }
        heads = tuple(sorted(header.id for header in headers if header.id not in referenced))
        cache: dict[str, str] = {}
        try:
            commitments = [
                self._node_commitment(by_id[head], by_id, cache, set()) for head in heads
            ]
        except RecursionError:
            raise ValueError("state_dag_too_deep") from None
        material = "\n".join(sorted(commitments)).encode("ascii")
        root = hashlib.sha3_256(b"eira-merkle-dag-v1\x00" + material).hexdigest()
        return MerkleSnapshot(root=root, headers=headers, heads=heads)

    def diff(
        self,
        local: Iterable[State | Mapping[str, Any] | StateHeader],
        remote: Iterable[State | Mapping[str, Any] | StateHeader],
    ) -> SyncDiff:
        local_snapshot = self.snapshot(local)
        remote_snapshot = self.snapshot(remote)
        local_hashes = {header.hash for header in local_snapshot.headers}
        remote_hashes = {header.hash for header in remote_snapshot.headers}
        return SyncDiff(
            local_root=local_snapshot.root,
            remote_root=remote_snapshot.root,
            missing_from_local=tuple(
                header.hash
                for header in remote_snapshot.headers
                if header.hash not in local_hashes
            ),
            missing_from_remote=tuple(
                header.hash
                for header in local_snapshot.headers
                if header.hash not in remote_hashes
            ),
        )

    def reconcile(
        self,
        local: Iterable[State | Mapping[str, Any] | StateHeader],
        remote: Iterable[State | Mapping[str, Any] | StateHeader],
    ) -> ForkResolution:
        local_headers = self._headers(local)
        remote_headers = self._headers(remote)
        combined_by_hash = {header.hash: header for header in (*local_headers, *remote_headers)}
        combined = tuple(
            sorted(
                combined_by_hash.values(),
                key=lambda item: (item.timestamp_ns, item.id, item.hash),
            )
        )
        by_id: dict[str, StateHeader] = {}
        conflicting_ids: set[str] = set()
        for header in combined:
            current = by_id.get(header.id)
            if current is not None and current.hash != header.hash:
                conflicting_ids.add(header.id)
            else:
                by_id[header.id] = header

        if conflicting_ids:
            conflict_material = "\n".join(
                f"{header.id}:{header.hash}:{header.previous_state_id or ''}"
                for header in combined
            ).encode("utf-8")
            root = hashlib.sha3_256(
                b"eira-merkle-conflict-v1\x00" + conflict_material
            ).hexdigest()
            referenced = {
                header.previous_state_id
                for header in combined
                if header.previous_state_id is not None
            }
            heads = tuple(sorted({h.id for h in combined if h.id not in referenced}))
            snapshot = MerkleSnapshot(root, combined, heads)
            return ForkResolution(snapshot, None, tuple(sorted(conflicting_ids)))

        snapshot = self.snapshot(combined)
        if len(snapshot.heads) > 1:
            # More than one tip is a fork/partition until an explicit policy resolves it.
            return ForkResolution(snapshot, None, snapshot.heads)
        canonical_head = snapshot.heads[0] if snapshot.heads else None
        return ForkResolution(snapshot, canonical_head, ())
