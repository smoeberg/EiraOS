from __future__ import annotations

import pytest

import app.core_rust as core_rust
from app.daemons import stated


class FakePythonStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path


def test_auto_backend_falls_back_when_native_library_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIRA_STATE_BACKEND", "auto")
    monkeypatch.setenv("EIRA_STATE_DB", ":memory:")

    def unavailable(_db_path: str) -> None:
        raise core_rust.RustBackendUnavailable("native library missing")

    monkeypatch.setattr(core_rust, "RustStateStore", unavailable)
    monkeypatch.setattr(stated, "StateStore", FakePythonStore)

    store = stated._create_store()

    assert isinstance(store, FakePythonStore)
    assert store.db_path == ":memory:"


def test_auto_backend_does_not_hide_native_store_open_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIRA_STATE_BACKEND", "auto")
    monkeypatch.setenv("EIRA_STATE_DB", ":memory:")

    def broken(_db_path: str) -> None:
        raise core_rust.RustStateError("SQLite open failed")

    monkeypatch.setattr(core_rust, "RustStateStore", broken)
    monkeypatch.setattr(stated, "StateStore", FakePythonStore)

    with pytest.raises(core_rust.RustStateError, match="SQLite open failed"):
        stated._create_store()


def test_explicit_rust_backend_never_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIRA_STATE_BACKEND", "rust")
    monkeypatch.setenv("EIRA_STATE_DB", ":memory:")

    def unavailable(_db_path: str) -> None:
        raise core_rust.RustBackendUnavailable("native library missing")

    def python_store_must_not_run(_db_path: str) -> None:
        raise AssertionError("explicit Rust mode must not instantiate Python store")

    monkeypatch.setattr(core_rust, "RustStateStore", unavailable)
    monkeypatch.setattr(stated, "StateStore", python_store_must_not_run)

    with pytest.raises(core_rust.RustBackendUnavailable, match="native library missing"):
        stated._create_store()


def test_explicit_python_backend_does_not_load_rust(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIRA_STATE_BACKEND", "python")
    monkeypatch.setenv("EIRA_STATE_DB", ":memory:")

    def rust_must_not_run(_db_path: str) -> None:
        raise AssertionError("explicit Python mode must not load Rust store")

    monkeypatch.setattr(core_rust, "RustStateStore", rust_must_not_run)
    monkeypatch.setattr(stated, "StateStore", FakePythonStore)

    assert isinstance(stated._create_store(), FakePythonStore)
