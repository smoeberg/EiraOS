"""Installed daemons must not write relative to their read-only WorkingDirectory."""

from app import session_store


def test_installed_units_point_the_shared_db_at_data(monkeypatch):
    monkeypatch.delenv("EIRA_DB_PATH", raising=False)
    monkeypatch.setenv("EIRA_APP_DB", "/tmp/eira-app-test/eira-app.db")
    assert session_store.get_db_path() == "/tmp/eira-app-test/eira-app.db"


def test_explicit_db_path_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("EIRA_DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("EIRA_APP_DB", "/data/eira-app.db")
    assert session_store.get_db_path() == str(tmp_path / "x.db")
