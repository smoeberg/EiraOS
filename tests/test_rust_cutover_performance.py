from __future__ import annotations

import copy
import os
import shutil
import statistics
import subprocess
import time
from pathlib import Path

import pytest

from app.core.state import State
from app.core.store import StateStore
from app.core_rust import RustStateError, RustStateStore

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def rust_library() -> Path:
    cargo = shutil.which("cargo")
    if cargo is None:
        pytest.skip("Rust toolchain is not installed in this validation environment")
    subprocess.run(
        [cargo, "build", "--release", "-p", "eira-stated"],
        cwd=REPO_ROOT,
        check=True,
        timeout=600,
    )
    candidates = (
        REPO_ROOT / "target" / "release" / "libeira_stated.so",
        REPO_ROOT / "target" / "release" / "libeira_stated.dylib",
        REPO_ROOT / "target" / "release" / "eira_stated.dll",
    )
    library = next((path for path in candidates if path.exists()), None)
    if library is None:
        pytest.skip("eira-stated cdylib is unavailable on this platform")
    return library


def _chain(length: int) -> list[State]:
    states: list[State] = []
    previous = None
    for version in range(1, length + 1):
        state = State(
            version=version,
            timestamp_ns=version,
            type="BenchmarkState",
            payload={"version": version, "text": "ærlig øvelse", "values": list(range(12))},
            previous_state_id=previous.id if previous else None,
        )
        states.append(state)
        previous = state
    return states


def _append_latencies(store: StateStore | RustStateStore, states: list[State]) -> list[int]:
    samples: list[int] = []
    for state in states:
        started = time.perf_counter_ns()
        store.append(state)
        samples.append(time.perf_counter_ns() - started)
    return samples


def _percentile_95(samples: list[int]) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] / 1_000_000


def test_python_and_rust_state_compatibility(rust_library: Path) -> None:
    states = _chain(40)
    python_store = StateStore(":memory:")
    with RustStateStore(":memory:", rust_library) as rust_store:
        for state in states:
            python_store.append(state)
            rust_store.append(state)
        assert [state.model_dump(mode="json") for state in rust_store.list_states()] == [
            state.model_dump(mode="json") for state in python_store.list_states()
        ]
        assert rust_store.get_by_hash(states[-1].hash) == states[-1]
        assert rust_store.get_history(states[-1].id) == list(reversed(states))


def test_tampered_state_is_rejected_by_rust_before_insert(rust_library: Path) -> None:
    original = _chain(1)[0]
    value = copy.deepcopy(original.model_dump(mode="json"))
    value["payload"]["text"] = "tampered"
    tampered = State.model_validate(value)
    with RustStateStore(":memory:", rust_library) as rust_store:
        with pytest.raises(RustStateError, match="hash"):
            rust_store.append(tampered)
        assert rust_store.count() == 0


def test_rust_append_p95_is_under_one_millisecond(rust_library: Path) -> None:
    states = _chain(500)
    python_store = StateStore(":memory:")
    with RustStateStore(":memory:", rust_library) as rust_store:
        python_samples = _append_latencies(python_store, states)
        rust_samples = _append_latencies(rust_store, states)

    rust_p95_ms = _percentile_95(rust_samples[25:])
    target_ms = float(os.environ.get("EIRA_RUST_APPEND_P95_MS", "1.0"))
    assert rust_p95_ms < target_ms, (
        f"Rust append p95 {rust_p95_ms:.3f} ms exceeds {target_ms:.3f} ms"
    )
    assert statistics.median(rust_samples[25:]) < statistics.median(python_samples[25:])
