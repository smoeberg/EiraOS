"""Installable EiraOS ISO: autoinstall policy, first-boot binding and remastering.

The real ISO is built in CI from the official Ubuntu live-server ISO
(.github/workflows/packaging-acceptance.yml). These tests cover what can be
checked without network access: the installer never wipes a disk on its own,
the first-boot script binds the right user, and build_iso.sh lays out the
medium the way autoinstall.yaml and eira-postinstall.sh expect.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / "packaging" / "installer"


def _autoinstall() -> dict:
    data = yaml.safe_load((INSTALLER / "autoinstall.yaml").read_text(encoding="utf-8"))
    return data["autoinstall"]


def test_installer_asks_for_disk_and_user_and_never_wipes_on_its_own():
    config = _autoinstall()
    assert config["version"] == 1
    assert {"storage", "identity", "network"} <= set(config["interactive-sections"])
    # A preset storage layout would be applied without the user choosing a disk.
    assert "storage" not in config
    assert "identity" not in config


def test_installer_installs_eira_from_the_medium():
    config = _autoinstall()
    commands = "\n".join(config["late-commands"])
    assert "/cdrom/eira/" in commands
    assert "eira-postinstall.sh" in commands
    assert config["source"]["id"] == "ubuntu-server-minimal"
    assert {"greetd", "labwc", "network-manager"} <= set(config["packages"])


def _firstboot(tmp_path: Path, passwd: str) -> subprocess.CompletedProcess[str]:
    greetd = tmp_path / "config.toml"
    shutil.copy(REPO / "packaging" / "session" / "config" / "greetd" / "config.toml", greetd)
    passwd_file = tmp_path / "passwd"
    passwd_file.write_text(passwd, encoding="utf-8")
    env = {
        **os.environ,
        "EIRA_FIRSTBOOT_DRY_RUN": "1",
        "EIRA_GREETD_CONF": str(greetd),
        "EIRA_PASSWD_FILE": str(passwd_file),
    }
    return subprocess.run(
        ["sh", str(INSTALLER / "eira-firstboot")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_firstboot_binds_first_human_user_to_greetd(tmp_path):
    result = _firstboot(
        tmp_path,
        "root:x:0:0::/root:/bin/bash\n"
        "syslog:x:104:110::/home/syslog:/usr/sbin/nologin\n"
        "svc:x:1001:1001::/srv:/usr/sbin/nologin\n"
        "soren:x:1000:1000:Soren:/home/soren:/bin/bash\n"
        "nobody:x:65534:65534::/nonexistent:/usr/sbin/nologin\n",
    )
    assert result.returncode == 0, result.stderr
    config = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert 'user = "soren"' in config
    assert 'user = "ubuntu"' not in config


def test_firstboot_fails_without_a_human_user(tmp_path):
    result = _firstboot(tmp_path, "root:x:0:0::/root:/bin/bash\n")
    assert result.returncode != 0
    assert 'user = "ubuntu"' in (tmp_path / "config.toml").read_text(encoding="utf-8")


def test_postinstall_uses_every_file_build_iso_stages():
    script = (REPO / "scripts" / "build_iso.sh").read_text(encoding="utf-8")
    postinstall = (INSTALLER / "eira-postinstall.sh").read_text(encoding="utf-8")
    for staged in (
        "eira-os-core.deb",
        "eira-firstboot",
        "eira-firstboot.service",
        "session/greetd/config.toml",
        "session/labwc/rc.xml",
        "session/labwc/autostart",
    ):
        assert f"$STAGE/eira/{staged}" in script
        assert f"$SRC/{staged}" in postinstall


@pytest.mark.skipif(shutil.which("xorriso") is None, reason="xorriso not installed")
def test_build_iso_remasters_a_base_iso(tmp_path):
    base = tmp_path / "base"
    (base / "boot" / "grub").mkdir(parents=True)
    (base / "boot" / "grub" / "grub.cfg").write_text(
        'menuentry "Try or Install Ubuntu Server" {\n  linux /casper/vmlinuz ---\n}\n',
        encoding="utf-8",
    )
    base_iso = tmp_path / "ubuntu-24.04-live-server-amd64.iso"
    subprocess.run(
        ["xorriso", "-as", "mkisofs", "-quiet", "-o", str(base_iso), str(base)],
        check=True,
        capture_output=True,
    )
    deb = tmp_path / "eira-os-core.deb"
    deb.write_bytes(b"not a real package")
    out = tmp_path / "out"

    result = subprocess.run(
        [
            "bash",
            str(REPO / "scripts" / "build_iso.sh"),
            "--base-iso",
            str(base_iso),
            "--deb",
            str(deb),
            "--output-dir",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    iso = out / "EiraOS-1.0-RC1-amd64.iso"
    listing = subprocess.run(
        ["xorriso", "-indev", str(iso), "-find", "/", "-type", "f"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for path in (
        "/autoinstall.yaml",
        "/eira/eira-os-core.deb",
        "/eira/eira-postinstall.sh",
        "/eira/eira-firstboot",
        "/eira/session/greetd/config.toml",
    ):
        assert f"'{path}'" in listing

    grub = tmp_path / "grub.cfg"
    subprocess.run(
        ["xorriso", "-osirrox", "on", "-indev", str(iso), "-extract", "/boot/grub/grub.cfg", str(grub)],
        check=True,
        capture_output=True,
    )
    assert "Installér EiraOS" in grub.read_text(encoding="utf-8")
    assert (out / "EiraOS-1.0-RC1-amd64.iso.sha3-256").read_text(encoding="utf-8").strip()


def test_build_iso_requires_a_base_iso(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "EIRA_BASE_ISO"}
    result = subprocess.run(
        ["bash", str(REPO / "scripts" / "build_iso.sh"), "--output-dir", str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if shutil.which("xorriso") is None:
        assert result.returncode == 69
    else:
        assert result.returncode == 64
        assert "fetch_ubuntu_iso.sh" in result.stderr
