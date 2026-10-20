from __future__ import annotations

import copy
import ctypes
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.core.state import State

REPO_ROOT = Path(__file__).resolve().parents[1]


class NativeStateEngine:
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


@pytest.fixture(scope="module")
def ffi_engine() -> NativeStateEngine:
    cargo = shutil.which("cargo")
    if cargo is None:
        pytest.skip("Rust toolchain is not installed in this validation environment")
    subprocess.run(
        [cargo, "build", "--release", "-p", "eira-core"],
        cwd=REPO_ROOT,
        check=True,
        timeout=300,
    )
    library = REPO_ROOT / "target" / "release" / "libeira_core.so"
    if not library.exists():
        pytest.skip("Native eira-core cdylib is unavailable on this platform")
    return NativeStateEngine(library)


def _chain(length: int = 3) -> list[State]:
    states: list[State] = []
    previous = None
    for version in range(1, length + 1):
        state = State(
            type="DocumentState",
            version=version,
            timestamp_ns=version,
            previous_state_id=previous.id if previous else None,
            payload={"version": version, "text": "ærlig øvelse"},
        )
        states.append(state)
        previous = state
    return states


def test_canonical_hash_fixture_matches_android_binding() -> None:
    state = State(
        id="00000000-0000-0000-0000-000000000001",
        version=1,
        timestamp_ns=1,
        type="DocumentState",
        payload={"æ": "ø", "a": 1},
    )
    assert state.hash == (
        "b171d45f3bd8ffba4cfcbcbdf8275da4512db8ea934dd3c31fe5d0030c6fbf43"
    )


def test_python_and_ffi_hash_consistency(ffi_engine: NativeStateEngine) -> None:
    state = _chain(1)[0]
    value = state.model_dump(mode="json")
    assert ffi_engine.compute_hash(value) == state.hash


def test_chain_validation_across_platforms(ffi_engine: NativeStateEngine) -> None:
    values = [state.model_dump(mode="json") for state in _chain()]
    assert ffi_engine.validate_chain(values)


def test_tampered_chain_detected_by_ffi(ffi_engine: NativeStateEngine) -> None:
    values = [state.model_dump(mode="json") for state in _chain()]
    tampered = copy.deepcopy(values)
    tampered[1]["payload"]["text"] = "tampered"
    assert not ffi_engine.validate_chain(tampered)

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

