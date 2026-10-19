from __future__ import annotations

import hashlib
from uuid import UUID, uuid5

from app.core.state import State
from app.fleet.merkle_sync import MerkleSyncEngine, StateHeader
import pytest


_NAMESPACE = UUID("4f8b8a9d-cb4f-4ad4-bd37-4b15a77d96f0")


def _state(label: str, previous: State | None = None) -> State:
    return State(
        id=uuid5(_NAMESPACE, label),
        timestamp_ns=len(label) + (previous.timestamp_ns + 1 if previous else 1),
        type="test",
        payload={"label": label},
        previous_state_id=previous.id if previous else None,
    )


def _hash(label: str) -> str:
    return hashlib.sha3_256(label.encode("utf-8")).hexdigest()


def test_snapshot_is_deterministic_and_commits_to_parent_chain():
    engine = MerkleSyncEngine()
    root = _state("root")
    child = _state("child", root)
    other_child = _state("other-child", root)

    first = engine.snapshot([root, child])
    reordered = engine.snapshot([child, root])
    forked = engine.snapshot([root, other_child])

    assert first.root == reordered.root
    assert first.root != forked.root
    assert first.heads == (str(child.id),)
    assert first.headers[0].hash == root.hash


def test_diff_returns_only_missing_hash_segments_in_each_direction():
    engine = MerkleSyncEngine()
    root = _state("root")
    left = _state("left", root)
    right = _state("right", root)

    diff = engine.diff([root, left], [root, right])

    assert diff.missing_from_local == (right.hash,)
    assert diff.missing_from_remote == (left.hash,)
    assert not diff.in_sync


def test_mutual_sync_rounds_reach_same_merkle_root():
    engine = MerkleSyncEngine()
    root = _state("root")
    left = _state("left", root)
    right = _state("right", root)
    peer_a = {state.hash: state for state in (root, left)}
    peer_b = {state.hash: state for state in (root, right)}

    # Each round transmits only the peer's missing immutable states.
    for _ in range(3):
        delta = engine.diff(peer_a.values(), peer_b.values())
        for state_hash in delta.missing_from_local:
            peer_a[state_hash] = peer_b[state_hash]
        for state_hash in delta.missing_from_remote:
            peer_b[state_hash] = peer_a[state_hash]
        if engine.diff(peer_a.values(), peer_b.values()).in_sync:
            break

    final = engine.diff(peer_a.values(), peer_b.values())
    assert final.in_sync
    assert final.local_root == final.remote_root
    assert set(peer_a) == set(peer_b) == {root.hash, left.hash, right.hash}


def test_reconcile_marks_fork_conflict_without_choosing_canonical_head():
    engine = MerkleSyncEngine()
    root = _state("root")
    left = _state("left", root)
    right = _state("right", root)

    result = engine.reconcile([root, left], [root, right])

    assert result.has_conflict
    assert result.canonical_head is None
    assert result.conflicting_ids == tuple(sorted((str(left.id), str(right.id))))
    assert len(result.snapshot.heads) == 2


def test_reconcile_same_state_id_with_different_hash_fails_closed():
    engine = MerkleSyncEngine()
    shared_id = str(uuid5(_NAMESPACE, "collision"))
    left = StateHeader(shared_id, 1, _hash("left-content"), None, 1)
    right = StateHeader(shared_id, 1, _hash("right-content"), None, 2)

    result = engine.reconcile([left], [right])

    assert result.has_conflict
    assert result.canonical_head is None
    assert result.conflicting_ids == (shared_id,)
    assert len({header.hash for header in result.snapshot.headers}) == 2


def test_snapshot_rejects_state_payload_tampering_after_hash_creation():
    engine = MerkleSyncEngine()
    state = _state("original")
    state.payload["label"] = "tampered"

    with pytest.raises(ValueError, match="state_hash_verification_failed"):
        engine.snapshot([state])


def test_snapshot_rejects_duplicate_id_and_malformed_hash():
    engine = MerkleSyncEngine()
    state_id = str(uuid5(_NAMESPACE, "duplicate"))
    first = StateHeader(state_id, 1, _hash("one"), None)
    second = StateHeader(state_id, 1, _hash("two"), None)

    with pytest.raises(ValueError, match="conflicting_immutable_state_id"):
        engine.snapshot([first, second])
    with pytest.raises(ValueError, match="invalid_state_header"):
        engine.snapshot([StateHeader("bad", 1, "not-a-sha3-hash", None)])


def test_snapshot_rejects_cycle_even_when_dag_has_no_head():
    engine = MerkleSyncEngine()
    first = StateHeader("first", 1, _hash("first"), "second", 1)
    second = StateHeader("second", 1, _hash("second"), "first", 2)

    with pytest.raises(ValueError, match="state_dag_cycle_detected"):
        engine.snapshot([first, second])


def test_deep_dag_recursion_failure_is_converted_to_safe_value_error():
    engine = MerkleSyncEngine()
    headers = []
    previous_id = None
    for index in range(1200):
        state_id = f"state-{index}"
        headers.append(
            StateHeader(state_id, 1, _hash(state_id), previous_id, index + 1)
        )
        previous_id = state_id

    with pytest.raises(ValueError, match="state_dag_too_deep"):
        engine.snapshot(headers)


def test_missing_parent_is_explicitly_committed_until_ancestor_arrives():
    engine = MerkleSyncEngine()
    root = _state("root")
    child = _state("child", root)

    partial = engine.snapshot([child])
    complete = engine.snapshot([root, child])

    assert partial.root != complete.root
    assert engine.diff([child], [root, child]).missing_from_local == (root.hash,)
    assert engine.diff([root, child], [child]).missing_from_remote == (root.hash,)
