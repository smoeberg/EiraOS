from __future__ import annotations

import ctypes
import json
import os
import threading
from pathlib import Path
from typing import Any
from uuid import UUID

from app.core.state import State


class RustBackendUnavailable(RuntimeError):
    pass


class RustStateError(RuntimeError):
    pass


def _library_candidates() -> list[Path]:
    configured = os.environ.get("EIRA_STATED_LIB", "").strip()
    if configured:
        return [Path(configured).expanduser()]
    root = Path(__file__).resolve().parents[1]
    names = ("libeira_stated.so", "libeira_stated.dylib", "eira_stated.dll")
    build_paths = [
        root / "target" / profile / name
        for profile in ("release", "debug")
        for name in names
    ]
    installed_paths = [
        prefix / name
        for prefix in (Path("/usr/lib/eira"), Path("/usr/local/lib/eira"))
        for name in names
    ]
    return [*build_paths, *installed_paths]


def find_rust_library() -> Path | None:
    return next((path for path in _library_candidates() if path.is_file()), None)


class _NativeLibrary:
    def __init__(self, path: Path) -> None:
        try:
            self.value = ctypes.CDLL(str(path))
        except OSError as exc:
            raise RustBackendUnavailable(f"Cannot load Rust stated library: {exc}") from exc

        self.value.eira_stated_open.argtypes = [ctypes.c_char_p]
        self.value.eira_stated_open.restype = ctypes.c_void_p
        self.value.eira_stated_close.argtypes = [ctypes.c_void_p]
        self.value.eira_stated_close.restype = None
        self.value.eira_stated_append_json.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.value.eira_stated_append_json.restype = ctypes.c_int32
        self.value.eira_stated_get_by_id_json.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.value.eira_stated_get_by_id_json.restype = ctypes.c_void_p
        self.value.eira_stated_get_by_hash_json.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.value.eira_stated_get_by_hash_json.restype = ctypes.c_void_p
        self.value.eira_stated_list_json.argtypes = [ctypes.c_void_p]
        self.value.eira_stated_list_json.restype = ctypes.c_void_p
        self.value.eira_stated_count.argtypes = [ctypes.c_void_p]
        self.value.eira_stated_count.restype = ctypes.c_int64
        self.value.eira_stated_last_error.argtypes = []
        self.value.eira_stated_last_error.restype = ctypes.c_void_p
        self.value.eira_stated_free_string.argtypes = [ctypes.c_void_p]
        self.value.eira_stated_free_string.restype = None

    def take_string(self, pointer: int | None) -> str:
        if not pointer:
            raise RustStateError(self.last_error() or "Rust stated returned a null pointer")
        try:
            return ctypes.string_at(pointer).decode("utf-8")
        finally:
            self.value.eira_stated_free_string(pointer)

    def last_error(self) -> str:
        pointer = self.value.eira_stated_last_error()
        if not pointer:
            return ""
        try:
            return ctypes.string_at(pointer).decode("utf-8", errors="replace")
        finally:
            self.value.eira_stated_free_string(pointer)


class RustStateStore:
    """StateStore-compatible owner of the eira-stated C-FFI handle."""

    def __init__(self, db_path: str = ":memory:", library_path: str | Path | None = None) -> None:
        path = Path(library_path) if library_path else find_rust_library()
        if path is None:
            raise RustBackendUnavailable(
                "eira-stated native library is not built; run cargo build --release -p eira-stated"
            )
        self._native = _NativeLibrary(path)
        self._lock = threading.RLock()
        self._handle = self._native.value.eira_stated_open(os.fsencode(db_path))
        if not self._handle:
            raise RustStateError(self._native.last_error() or "Failed to open Rust state store")

    def _ensure_open(self) -> int:
        if not self._handle:
            raise RustStateError("Rust state store is closed")
        return int(self._handle)

    @staticmethod
    def _encode_state(state: State) -> bytes:
        return json.dumps(
            state.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")

    @staticmethod
    def _decode_state(value: dict[str, Any] | None) -> State | None:
        return State.model_validate(value) if value is not None else None

    def append(self, state: State) -> None:
        with self._lock:
            result = self._native.value.eira_stated_append_json(
                self._ensure_open(), self._encode_state(state)
            )
            if result != 0:
                raise RustStateError(self._native.last_error() or f"Rust append failed ({result})")

    def _get(self, value: str, *, by_hash: bool) -> State | None:
        with self._lock:
            function = (
                self._native.value.eira_stated_get_by_hash_json
                if by_hash
                else self._native.value.eira_stated_get_by_id_json
            )
            pointer = function(self._ensure_open(), value.encode("utf-8"))
            decoded = json.loads(self._native.take_string(pointer))
        return self._decode_state(decoded)

    def get_by_id(self, state_id: UUID) -> State | None:
        return self._get(str(state_id), by_hash=False)

    def get_by_hash(self, state_hash: str) -> State | None:
        return self._get(state_hash, by_hash=True)

    def list_states(self) -> list[State]:
        with self._lock:
            pointer = self._native.value.eira_stated_list_json(self._ensure_open())
            values = json.loads(self._native.take_string(pointer))
        return [State.model_validate(value) for value in values]

    def get_history(self, latest_state_id: UUID) -> list[State]:
        history: list[State] = []
        current_id: UUID | None = latest_state_id
        while current_id is not None:
            state = self.get_by_id(current_id)
            if state is None:
                break
            history.append(state)
            current_id = state.previous_state_id
        return history

    def count(self) -> int:
        with self._lock:
            value = int(self._native.value.eira_stated_count(self._ensure_open()))
            if value < 0:
                raise RustStateError(self._native.last_error() or "Rust count failed")
            return value

    def close(self) -> None:
        with self._lock:
            if self._handle:
                self._native.value.eira_stated_close(self._handle)
                self._handle = None

    def __enter__(self) -> RustStateStore:
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
