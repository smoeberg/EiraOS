from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
APPARMOR_DIR = REPO_ROOT / "packaging" / "apparmor"
DAEMONS = ("stated", "identityd", "fleetd", "veritasd", "intentd", "graphd")


def _debian_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    current = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line:
            current = ""
            continue
        if raw_line[0].isspace() and current:
            fields[current] += " " + raw_line.strip()
            continue
        current, value = raw_line.split(":", 1)
        fields[current] = value.strip()
    return fields


def test_all_daemons_have_least_privilege_apparmor_profiles() -> None:
    for daemon in DAEMONS:
        profile = APPARMOR_DIR / f"usr.bin.eira-{daemon}"
        text = profile.read_text(encoding="utf-8")
        assert f"/usr/bin/eira-{daemon}" in text
        assert "/run/eira/*.sock rwk," in text
        assert "/var/log/eira/** rw," in text
        assert "deny @{HOME}/** rwklx," in text
        assert "flags=(attach_disconnected,mediate_deleted)" in text

    stated = (APPARMOR_DIR / "usr.bin.eira-stated").read_text(encoding="utf-8")
    assert "/data/eira.db rwk," in stated
    assert "/data/eira.db-{journal,shm,wal} rwk," in stated
    assert "deny network inet," in stated
    assert "deny network inet6," in stated

    identity = (APPARMOR_DIR / "usr.bin.eira-identityd").read_text(encoding="utf-8")
    assert "network inet stream," in identity
    assert "/etc/eira/trust/** r," in identity


@pytest.mark.skipif(
    shutil.which("apparmor_parser") is None,
    reason="AppArmor userspace parser is not installed in this validation runtime",
)
def test_apparmor_profiles_parse_on_ubuntu() -> None:
    result = subprocess.run(
        ["apparmor_parser", "-Q", "-q", *map(str, sorted(APPARMOR_DIR.glob("usr.bin.eira-*")))],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_debian_manifest_is_complete_and_offline_install_safe() -> None:
    fields = _debian_fields(REPO_ROOT / "packaging" / "debian" / "control")
    assert fields["Source"] == "eira-os-core"
    assert fields["Package"] == "eira-os-core"
    dependencies = fields["Depends"]
    for dependency in (
        "apparmor",
        "python3-cryptography",
        "python3-httpx",
        "python3-pydantic",
        "python3-websockets",
    ):
        assert dependency in dependencies

    postinst = (REPO_ROOT / "packaging" / "debian" / "postinst").read_text(
        encoding="utf-8"
    )
    assert "token_hex(32)" in postinst
    assert "pip install" not in postinst
    assert "curl " not in postinst
    assert "wget " not in postinst


def test_iso_builder_targets_noble_and_embeds_local_deb() -> None:
    script = (REPO_ROOT / "scripts" / "build_iso.sh").read_text(encoding="utf-8")
    assert "--distribution noble" in script
    assert "--mode ubuntu" in script
    assert "config/packages.chroot/eira-os-core.deb" in script
    assert "ubuntu-desktop-minimal" in script
    assert "systemctl enable eira.target" in script
    assert "adduser ubuntu eira" in script


def test_session_and_systemd_boot_integration_are_hardened() -> None:
    desktop = (REPO_ROOT / "packaging" / "session" / "eira-session.desktop").read_text(
        encoding="utf-8"
    )
    assert "Exec=/usr/bin/eira-session" in desktop
    assert "TryExec=/usr/bin/eira-session" in desktop
    assert "DesktopNames=EiraOS;GNOME;" in desktop

    for daemon in DAEMONS:
        unit = (REPO_ROOT / "systemd" / f"eira-{daemon}.service").read_text(
            encoding="utf-8"
        )
        assert f"ExecStart=/usr/bin/eira-{daemon}" in unit
        assert f"AppArmorProfile=/usr/bin/eira-{daemon}" in unit
        assert "NoNewPrivileges=true" in unit
        assert "ProtectSystem=strict" in unit
        assert "EnvironmentFile=-/etc/eira/eira.conf" in unit

    fleet = (REPO_ROOT / "systemd" / "eira-fleetd.service").read_text(encoding="utf-8")
    assert "EIRA_FLEET_WS_HOST=127.0.0.1" in fleet
    assert "IPAddressDeny=any" in fleet
    assert "IPAddressAllow=localhost" in fleet
    assert "0.0.0.0" not in fleet


def test_packaging_scripts_are_executable_shell_files() -> None:
    scripts = (
        REPO_ROOT / "scripts" / "build_deb.sh",
        REPO_ROOT / "scripts" / "build_iso.sh",
        REPO_ROOT / "packaging" / "debian" / "rules",
        REPO_ROOT / "packaging" / "debian" / "postinst",
        REPO_ROOT / "packaging" / "bin" / "eira-daemon",
        REPO_ROOT / "packaging" / "session" / "eira-session",
    )
    for script in scripts:
        assert script.read_text(encoding="utf-8").startswith("#!")
        assert stat.S_IMODE(script.stat().st_mode) & stat.S_IXUSR

    env = os.environ.copy()
    for script in scripts:
        if script.name in {"rules", "postinst"}:
            continue
        result = subprocess.run(
            ["bash", "-n", str(script)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
