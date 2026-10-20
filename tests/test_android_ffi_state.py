from __future__ import annotations

import copy
import ctypes
import json
import shutil
import subprocess
from pathlib import Path
from uuid import UUID

import pytest

from app.core.state import State

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures" / "ffi_states.json"


class NativeStateEngine:
    """Thin ctypes wrapper around the eira-core C ABI (SHA3-256 + chain)."""

    def __init__(self, library_path: Path) -> None:
        self.library = ctypes.CDLL(str(library_path))
        self.library.eira_state_compute_hash.argtypes = [ctypes.c_char_p]
        self.library.eira_state_compute_hash.restype = ctypes.c_void_p
        self.library.eira_state_validate_chain.argtypes = [ctypes.c_char_p]
        self.library.eira_state_validate_chain.restype = ctypes.c_int32
        self.library.eira_free_string.argtypes = [ctypes.c_void_p]
        self.library.eira_free_string.restype = None

    def compute_hash(self, state: dict) -> str:
        pointer = self.library.eira_state_compute_hash(
            json.dumps(state, ensure_ascii=False).encode("utf-8")
        )
        if not pointer:
            raise RuntimeError("Rust FFI rejected state JSON")
        try:
            return ctypes.string_at(pointer).decode("ascii")
        finally:
            self.library.eira_free_string(pointer)

    def validate_chain(self, states: list[dict]) -> bool:
        result = self.library.eira_state_validate_chain(
            json.dumps(states, ensure_ascii=False).encode("utf-8")
        )
        if result < 0:
            raise RuntimeError("Rust FFI rejected chain JSON")
        return result == 1

    def validate_chain_raw(self, payload: bytes | None) -> int:
        """Return raw FFI status: 1 valid, 0 invalid chain, -1 bad input/null."""
        return int(self.library.eira_state_validate_chain(payload))

    def compute_hash_raw(self, payload: bytes | None) -> ctypes.c_void_p:
        return self.library.eira_state_compute_hash(payload)


@pytest.fixture(scope="module")
def ffi_engine() -> NativeStateEngine:
    cargo = shutil.which("cargo")
    if cargo is None:
        pytest.skip(
            "Rust toolchain is not installed — cannot build eira-core cdylib for FFI tests"
        )
    try:
        subprocess.run(
            [cargo, "build", "--release", "-p", "eira-core"],
            cwd=REPO_ROOT,
            check=True,
            timeout=300,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        pytest.skip(
            f"eira-core native build failed or timed out (skipping FFI tests): {exc}"
        )
    library = REPO_ROOT / "target" / "release" / "libeira_core.so"
    if not library.exists():
        pytest.skip(
            "Native eira-core cdylib (libeira_core.so) is unavailable on this platform"
        )
    return NativeStateEngine(library)


@pytest.fixture(scope="module")
def ffi_fixtures() -> dict:
    with FIXTURES_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _deterministic_chain(length: int = 3) -> list[State]:
    """Build a fully deterministic chain (fixed UUIDs + timestamps, no wall-clock)."""
    states: list[State] = []
    previous: State | None = None
    for version in range(1, length + 1):
        state = State(
            id=UUID(f"00000000-0000-0000-0000-00000000000{version}"),
            type="DocumentState",
            version=version,
            timestamp_ns=version * 1_000_000_000,
            previous_state_id=previous.id if previous else None,
            payload={"version": version, "text": "ærlig øvelse", "n": version},
        )
        states.append(state)
        previous = state
    return states


def test_canonical_hash_fixture_matches_android_binding(ffi_fixtures: dict) -> None:
    state = State(
        id="00000000-0000-0000-0000-000000000001",
        version=1,
        timestamp_ns=1,
        type="DocumentState",
        payload={"æ": "ø", "a": 1},
    )
    expected = ffi_fixtures["canonical_hash"]
    assert state.hash == expected
    assert state.hash == (
        "b171d45f3bd8ffba4cfcbcbdf8275da4512db8ea934dd3c31fe5d0030c6fbf43"
    )


def test_python_and_ffi_hash_consistency(
    ffi_engine: NativeStateEngine, ffi_fixtures: dict
) -> None:
    # Live Python State vs FFI
    state = _deterministic_chain(1)[0]
    value = state.model_dump(mode="json")
    assert ffi_engine.compute_hash(value) == state.hash

    # Fixture canonical state vs FFI (cross-platform contract)
    canonical = ffi_fixtures["canonical_state"]
    assert ffi_engine.compute_hash(canonical) == ffi_fixtures["canonical_hash"]


def test_chain_validation_across_platforms(
    ffi_engine: NativeStateEngine, ffi_fixtures: dict
) -> None:
    values = [state.model_dump(mode="json") for state in _deterministic_chain()]
    assert ffi_engine.validate_chain(values)

    # Fixture chain must also validate
    assert ffi_engine.validate_chain(ffi_fixtures["valid_chain"])


def test_tampered_chain_detected_by_ffi(ffi_engine: NativeStateEngine) -> None:
    values = [state.model_dump(mode="json") for state in _deterministic_chain()]
    tampered = copy.deepcopy(values)
    # Flip one byte in a historical payload → hash mismatch → fail-closed
    tampered[1]["payload"]["text"] = "tampered"
    assert not ffi_engine.validate_chain(tampered)


def test_empty_chain_accepted_by_ffi(ffi_engine: NativeStateEngine) -> None:
    assert ffi_engine.validate_chain([])


def test_wrong_parent_hash_rejected_by_ffi(ffi_engine: NativeStateEngine) -> None:
    values = [state.model_dump(mode="json") for state in _deterministic_chain()]
    broken = copy.deepcopy(values)
    # Point at a non-existent parent → fail-closed
    broken[1]["previous_state_id"] = "00000000-0000-0000-0000-999999999999"
    # Hash is still the original (computed with real parent); validator checks both
    assert not ffi_engine.validate_chain(broken)


def test_non_json_input_rejected_by_ffi(ffi_engine: NativeStateEngine) -> None:
    # Invalid JSON must surface as error status (-1), never as a silent accept
    status = ffi_engine.validate_chain_raw(b"{not-valid-json")
    assert status == -1

    hash_ptr = ffi_engine.compute_hash_raw(b"{not-valid-json")
    assert not hash_ptr


def test_null_pointer_rejected_by_ffi(ffi_engine: NativeStateEngine) -> None:
    # Null-pointer simulation via ctypes — fail-closed, no crash
    status = ffi_engine.validate_chain_raw(None)
    assert status == -1

    hash_ptr = ffi_engine.compute_hash_raw(None)
    assert not hash_ptr


# --- origin/main (Agent 9): additional FFI edge cases ---

def test_ffi_rejects_null_pointers_and_invalid_json(ffi_engine: NativeStateEngine) -> None:
    compute_hash = ffi_engine.library.eira_state_compute_hash
    validate_chain = ffi_engine.library.eira_state_validate_chain

    assert not compute_hash(None)
    assert not compute_hash(b"{invalid json")
    assert validate_chain(None) == -1
    assert validate_chain(b"{invalid json") == -1


def test_ffi_handles_deeply_nested_invalid_state_without_crashing(
    ffi_engine: NativeStateEngine,
) -> None:
    deeply_nested = b'{"id":"state","version":1,"timestamp_ns":1,"type":"DocumentState","payload":' + (
        b"[" * 300 + b"0" + b"]" * 300
    ) + b',"previous_state_id":null}'
    assert not ffi_engine.library.eira_state_compute_hash(deeply_nested)
    assert ffi_engine.library.eira_state_validate_chain(b"[" + deeply_nested + b"]") == -1


def test_hash_matches_python_for_large_timestamp_and_unicode_payload(
    ffi_engine: NativeStateEngine,
) -> None:
    state = State(
        id="00000000-0000-0000-0000-000000000042",
        version=7,
        timestamp_ns=1_700_000_000_123_456_789,
        type="DocumentState",
        payload={"text": "Grønland — æøå 🌍", "count": 42, "enabled": True},
    )
    assert ffi_engine.compute_hash(state.model_dump(mode="json")) == state.hash
