"""One version for all of EiraOS (UDVIKLINGSPLAN F1.3).

VERSION is the single source. The package, the Rust workspace, the Tauri
app, the UI and the development bridge must all say the same, and the
package targets Ubuntu 26.04 (resolute).
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def test_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?", VERSION), VERSION


def test_debian_changelog_has_the_version_and_targets_resolute():
    first = (ROOT / "packaging" / "debian" / "changelog").read_text(encoding="utf-8").splitlines()[0]
    match = re.fullmatch(r"eira-os-core \((?P<version>[^)]+)\) (?P<dist>\S+); urgency=\w+", first)
    assert match, first
    upstream = match["version"].rsplit("-", 1)[0]
    # Debian writes a pre-release as ~ (1.0.0~rc1), SemVer as - (1.0.0-rc1).
    assert upstream == VERSION.replace("-", "~", 1)
    assert match["dist"] == "resolute"
    changelog = (ROOT / "packaging" / "debian" / "changelog").read_text(encoding="utf-8")
    assert "noble" not in changelog


def test_rust_workspace_and_every_crate_use_the_version():
    root = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    assert root["workspace"]["package"]["version"] == VERSION
    for member in root["workspace"]["members"]:
        package = tomllib.loads((ROOT / member / "Cargo.toml").read_text(encoding="utf-8"))["package"]
        assert package["version"] == {"workspace": True}, member


def test_desktop_app_and_ui_use_the_version():
    tauri_crate = tomllib.loads((ROOT / "ui" / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8"))
    assert tauri_crate["package"]["version"] == VERSION
    tauri_conf = json.loads((ROOT / "ui" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    assert tauri_conf["version"] == VERSION
    package = json.loads((ROOT / "ui" / "package.json").read_text(encoding="utf-8"))
    assert package["version"] == VERSION
    lock = json.loads((ROOT / "ui" / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["version"] == VERSION
    assert lock["packages"][""]["version"] == VERSION


def test_development_bridge_uses_the_version():
    for path in ("app/config.py", "app/http_bridge.py"):
        text = (ROOT / path).read_text(encoding="utf-8")
        found = re.findall(r'version\s*[:=]\s*(?:str\s*=\s*)?"([^"]+)"', text)
        assert found == [VERSION], (path, found)


def test_installer_and_user_agent_use_the_version():
    iso = (ROOT / "scripts" / "build_iso.sh").read_text(encoding="utf-8")
    assert "VERSION" in iso and "1.0-RC1" not in iso
    verifier = (ROOT / "app" / "auth" / "production_cert_verifier.py").read_text(encoding="utf-8")
    assert re.findall(r'"EiraOS/([^"]+)"', verifier) == [VERSION]


def test_build_script_takes_the_version_from_the_changelog():
    script = (ROOT / "scripts" / "build_deb.sh").read_text(encoding="utf-8")
    assert "dpkg-parsechangelog" in script
    assert "1.0~rc1" not in script
