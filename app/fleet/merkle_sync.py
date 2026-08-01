from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.core.state import State

EMPTY_ROOT = hashlib.sha3_256(b"eira-merkle-dag-v1\x00").hexdigest()


@dataclass(frozen=True)
class StateHeader:
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
        return cls(
            id=str(value["id"]),
            version=int(value.get("version", 1)),
            hash=str(value["hash"]),
            previous_state_id=(
                str(value["previous_state_id"])
                if value.get("previous_state_id")
                else None
            ),
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
    snapshot: MerkleSnapshot
    canonical_head: str | None
    conflicting_ids: tuple[str, ...]


class MerkleSyncEngine:
    """Build and reconcile Merkle commitments over immutable State DAGs."""

    @staticmethod
    def _headers(
        values: Iterable[State | Mapping[str, Any] | StateHeader],
    ) -> tuple[StateHeader, ...]:
        by_hash: dict[str, StateHeader] = {}
        for value in values:
            header = value if isinstance(value, StateHeader) else StateHeader.from_value(value)
            current = by_hash.get(header.hash)
            if current is not None and current != header:
                raise ValueError(f"Conflicting metadata for state hash {header.hash}")
            by_hash[header.hash] = header
        return tuple(sorted(by_hash.values(), key=lambda item: (item.timestamp_ns, item.id)))

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
            raise ValueError(f"Cycle detected in State DAG at {header.id}")
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
            return MerkleSnapshot(EMPTY_ROOT, (), ())

        by_id: dict[str, StateHeader] = {}
        conflicting_ids: set[str] = set()
        for header in headers:
            current = by_id.get(header.id)
            if current and current.hash != header.hash:
                conflicting_ids.add(header.id)
                if (header.version, header.timestamp_ns, header.hash) <= (
                    current.version,
                    current.timestamp_ns,
                    current.hash,
                ):
                    continue
            by_id[header.id] = header
        if conflicting_ids:
            raise ValueError(
                "Conflicting immutable states share IDs: "
                + ", ".join(sorted(conflicting_ids))
            )

        referenced = {
            header.previous_state_id
            for header in headers
            if header.previous_state_id is not None
        }
        heads = tuple(sorted(header.id for header in headers if header.id not in referenced))
        cache: dict[str, str] = {}
        commitments = [
            self._node_commitment(by_id[head], by_id, cache, set()) for head in heads
        ]
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
        remote_order = [header.hash for header in remote_snapshot.headers]
        local_order = [header.hash for header in local_snapshot.headers]
        return SyncDiff(
            local_root=local_snapshot.root,
            remote_root=remote_snapshot.root,
            missing_from_local=tuple(
                state_hash for state_hash in remote_order if state_hash not in local_hashes
            ),
            missing_from_remote=tuple(
                state_hash for state_hash in local_order if state_hash not in remote_hashes
            ),
        )

    def reconcile(
        self,
        local: Iterable[State | Mapping[str, Any] | StateHeader],
        remote: Iterable[State | Mapping[str, Any] | StateHeader],
    ) -> ForkResolution:
        combined = (*self._headers(local), *self._headers(remote))
        by_id: dict[str, StateHeader] = {}
        conflicts: set[str] = set()
        for header in combined:
            current = by_id.get(header.id)
            if current and current.hash != header.hash:
                conflicts.add(header.id)
                winner = max(
                    (current, header),
                    key=lambda item: (item.version, item.timestamp_ns, item.hash),
                )
                by_id[header.id] = winner
            else:
                by_id[header.id] = header
        snapshot = self.snapshot(by_id.values())
        candidates = [by_id[head] for head in snapshot.heads]
        canonical = (
            max(
                candidates,
                key=lambda item: (item.version, item.timestamp_ns, item.hash),
            ).id
            if candidates
            else None
        )
        return ForkResolution(snapshot, canonical, tuple(sorted(conflicts)))
