"""Guard: http_bridge må aldrig ind i prod-imaget eller GUI'en.

GUI'en bruger udelukkende Unix-socket IPC (Tauri Rust-bro). http_bridge er
en dev-entry; packaging/systemd og ui/src må ikke referere til den.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_IN_PROD = ("packaging", "ui/src")


def test_no_http_bridge_in_packaging_or_ui() -> None:
    for base in FORBIDDEN_IN_PROD:
        root = REPO_ROOT / base
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix in {".png", ".jpg", ".ico", ".woff", ".woff2"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert "http_bridge" not in text, f"http_bridge reference fundet i {path}"


def test_http_bridge_isolated_to_legacy_dev_entry() -> None:
    legacy = REPO_ROOT / "app" / "main.py"
    text = legacy.read_text(encoding="utf-8")
    assert "http_bridge" in text
    offenders = [
        p
        for p in (REPO_ROOT / "app").rglob("*.py")
        if p.name != "main.py" and "http_bridge" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == [], f"http_bridge lækkert ind i: {offenders}"
