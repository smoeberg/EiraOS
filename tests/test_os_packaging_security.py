from __future__ import annotations

import ast
import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
APPARMOR_DIR = REPO_ROOT / "packaging" / "apparmor"
DAEMON_POLICY_PATH = REPO_ROOT / "packaging" / "daemon-policy.json"


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


def _daemon_policy() -> dict[str, object]:
    return json.loads(DAEMON_POLICY_PATH.read_text(encoding="utf-8"))


def _runtime_daemon_names() -> set[str]:
    runner_path = REPO_ROOT / "app" / "daemons" / "runner.py"
    tree = ast.parse(runner_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "DAEMON_NAMES"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            assert isinstance(value, tuple)
            assert all(isinstance(name, str) for name in value)
            return set(value)
    raise AssertionError("app.daemons.runner.DAEMON_NAMES was not found")


def test_production_daemon_policy_matches_runtime_and_package() -> None:
    policy = _daemon_policy()
    production = policy["production_daemons"]
    prototypes = policy["prototype_daemons"]

    assert policy["schema_version"] == 1
    assert isinstance(production, list) and production
    assert isinstance(prototypes, list)
    assert len(production) == len(set(production)), "duplicate production daemon"
    assert len(prototypes) == len(set(prototypes)), "duplicate prototype daemon"
    assert set(production).isdisjoint(prototypes)
    assert set(production) | set(prototypes) == _runtime_daemon_names()

    launcher = (REPO_ROOT / "packaging" / "bin" / "eira-daemon").read_text(
        encoding="utf-8"
    )
    allowed_line = next(line for line in launcher.splitlines() if "stated|" in line)
    allowed_daemons = set(allowed_line.strip().split(")")[0].split("|"))
    assert allowed_daemons == set(production)

    service_files = {
        path.name.removeprefix("eira-").removesuffix(".service")
        for path in (REPO_ROOT / "systemd").glob("eira-*.service")
    }
    assert service_files == set(production)

    profile_names = {
        path.name.removeprefix("usr.bin.eira-")
        for path in APPARMOR_DIR.glob("usr.bin.eira-*")
    }
    assert profile_names == set(production)

    target = (REPO_ROOT / "systemd" / "eira.target").read_text(encoding="utf-8")
    target_services = set(re.findall(r"\beira-([a-z]+)\.service\b", target))
    assert target_services == set(production)

    rules = (REPO_ROOT / "packaging" / "debian" / "rules").read_text(encoding="utf-8")
    assert "packaging/daemon-policy.json" in rules
    assert '"production_daemons"' in rules
    assert "usr/share/eira-os/daemon-policy.json" in rules


def test_all_daemons_have_least_privilege_apparmor_profiles() -> None:
    production = _daemon_policy()["production_daemons"]
    for daemon in production:
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
def test_apparmor_profiles_parse_on_ubuntu(tmp_path) -> None:
    result = subprocess.run(
        [
            "apparmor_parser",
            "-Q",
            "-q",
            "--cache-loc",
            str(tmp_path / "apparmor-cache"),
            *map(str, sorted(APPARMOR_DIR.glob("usr.bin.eira-*"))),
        ],
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
        "eira-labwc (>= 0.20.3-1eira2)",  # R-6.2 patch
    ):
        assert dependency in dependencies

    postinst = (REPO_ROOT / "packaging" / "debian" / "postinst").read_text(
        encoding="utf-8"
    )
    assert "token_hex(32)" in postinst
    assert "pip install" not in postinst
    assert "curl " not in postinst
    assert "wget " not in postinst

    rules = (REPO_ROOT / "packaging" / "debian" / "rules").read_text(encoding="utf-8")
    assert "npm ci --prefix ui --ignore-scripts" in rules
    assert "dpkg-buildpackage" not in rules
    assert "dh_installsystemd --no-start" in rules

    deb_builder = (REPO_ROOT / "scripts" / "build_deb.sh").read_text(encoding="utf-8")
    assert "eira-os-core.deb.build-info.json" in deb_builder
    assert '"source_commit_verified"' in deb_builder
    assert '"sha3_256"' in deb_builder


def test_iso_builder_remasters_ubuntu_installer_and_embeds_local_deb() -> None:
    script = (REPO_ROOT / "scripts" / "build_iso.sh").read_text(encoding="utf-8")
    # Remaster the official installer; keep Ubuntu's boot records unchanged.
    assert "-boot_image any replay" in script
    assert "--base-iso" in script
    assert '-map "$STAGE/eira" /eira' in script
    assert '-map "$STAGE/autoinstall.yaml" /autoinstall.yaml' in script
    assert '"$INSTALLER/eira-firstboot"' in script
    assert "--ci-unattended" in script
    assert '"$INSTALLER/eira-postinstall.sh"' in script
    assert "lb config" not in script
    assert "package_commit_matches_iso_source" in script
    assert "EIRA_SOURCE_COMMIT" in script
    assert "build-info.json" in script

    fetch = (REPO_ROOT / "scripts" / "fetch_ubuntu_iso.sh").read_text(encoding="utf-8")
    assert "843938DF228D22F7B3742BC0D94AA3F0EFE21092" in fetch
    assert "VALIDSIG" in fetch
    assert "sha256sum --check" in fetch

    postinstall = (REPO_ROOT / "packaging" / "installer" / "eira-postinstall.sh").read_text(
        encoding="utf-8"
    )
    assert '$APT install -y "$SRC/eira-labwc.deb" "$SRC/eira-os-core.deb"' in postinstall
    assert "systemctl enable eira.target" in postinstall
    assert "systemctl enable eira-firstboot.service" in postinstall


def test_session_and_systemd_boot_integration_are_hardened() -> None:
    desktop = (REPO_ROOT / "packaging" / "session" / "eira-session.desktop").read_text(
        encoding="utf-8"
    )
    assert "Exec=/usr/bin/eira-session" in desktop
    assert "TryExec=/usr/bin/eira-session" in desktop
    assert "DesktopNames=EiraOS;GNOME;" in desktop

    session = (REPO_ROOT / "packaging" / "session" / "eira-session").read_text(
        encoding="utf-8"
    )
    assert 'if [ "$(id -u)" = "0" ]' in session
    assert "exec labwc" in session
    assert 'exec cage -- "$SHELL_BIN"' in session

    for daemon in _daemon_policy()["production_daemons"]:
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
        REPO_ROOT / "scripts" / "fetch_ubuntu_iso.sh",
        REPO_ROOT / "packaging" / "installer" / "eira-postinstall.sh",
        REPO_ROOT / "packaging" / "installer" / "eira-firstboot",
        REPO_ROOT / "packaging" / "debian" / "rules",
        REPO_ROOT / "packaging" / "debian" / "postinst",
        REPO_ROOT / "packaging" / "bin" / "eira-daemon",
        REPO_ROOT / "packaging" / "bin" / "eira-rights-apply",
        REPO_ROOT / "packaging" / "bin" / "eira-enroll",
        REPO_ROOT / "packaging" / "bin" / "eira-audit-verify",
        REPO_ROOT / "packaging" / "session" / "eira-session",
    )
    for script in scripts:
        assert script.read_text(encoding="utf-8").startswith("#!")
        assert stat.S_IMODE(script.stat().st_mode) & stat.S_IXUSR

    env = os.environ.copy()
    for script in scripts:
        if script.name == "rules":
            if shutil.which("make") is None:
                continue
            result = subprocess.run(
                ["make", "-n", "-f", str(script), "install"],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, result.stderr
            continue
        syntax_checker = "sh" if script.name == "postinst" else "bash"
        result = subprocess.run(
            [syntax_checker, "-n", str(script)],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_desktop_user_reaches_sockets_but_not_daemon_data() -> None:
    """ADR-0003: the substrate protects the Eira layer. Desktop users join
    eira-clients (sockets, IPC token), never eira (owns /data)."""
    postinst = (REPO_ROOT / "packaging" / "debian" / "postinst").read_text(encoding="utf-8")
    firstboot = (REPO_ROOT / "packaging" / "installer" / "eira-firstboot").read_text(encoding="utf-8")
    assert "addgroup --system eira-clients" in postinst
    assert "adduser --quiet eira eira-clients" in postinst
    assert 'gpasswd -d "$member" eira' in postinst  # upgrade moves users out of eira
    assert "chown root:eira-clients /etc/eira/eira.conf" in postinst
    assert 'usermod -aG eira-clients "$user"' in firstboot
    assert "-aG eira " not in firstboot and '-aG eira "' not in firstboot
    for unit in (REPO_ROOT / "systemd").glob("eira-*.service"):
        text = unit.read_text(encoding="utf-8")
        assert "SupplementaryGroups=eira-clients" in text, unit.name
        assert "RuntimeDirectoryMode=0751" in text, unit.name
        assert "UMask=0117" in text, unit.name  # data files stay eira:eira 0660
    from app.ipc import socket_security

    assert socket_security.SOCKET_GROUP == "eira-clients"
