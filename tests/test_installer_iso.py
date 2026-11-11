"""Installable EiraOS ISO: autoinstall policy, first-boot session and remastering.

The real ISO is built from the official Ubuntu Desktop 26.04 ISO and its
unattended CI variant is installed and booted in QEMU by
.github/workflows/packaging-acceptance.yml. These tests cover what can be
checked without network access: the real installer never wipes a disk on its
own, the CI image never leaks into the real one, first boot makes EiraOS the
user's session, and build_iso.sh lays out the medium the way the
post-install script expects.
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
BUILD_ISO = REPO / "scripts" / "build_iso.sh"


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["autoinstall"]


def test_installer_asks_for_disk_and_user_and_never_wipes_on_its_own():
    config = _yaml(INSTALLER / "autoinstall.yaml")
    assert config["version"] == 1
    assert {"storage", "identity", "network"} <= set(config["interactive-sections"])
    # A preset storage layout or identity would be applied without the user choosing.
    assert "storage" not in config
    assert "identity" not in config
    assert "shutdown" not in config


def test_installer_installs_ubuntu_desktop_then_eira_from_the_medium():
    config = _yaml(INSTALLER / "autoinstall.yaml")
    assert config["source"]["id"] == "ubuntu-desktop-minimal"
    commands = "\n".join(config["late-commands"])
    assert "/cdrom/eira/" in commands
    assert "eira-postinstall.sh" in commands
    assert "xwayland" in config["packages"]
    # Ubuntu's labwc (0.9) cannot withhold privileged protocols; eira-labwc
    # comes from the medium instead (EIRA-CONSENT-AGENT R-6.1).
    assert "labwc" not in config["packages"]


def test_ci_autoinstall_is_unattended_and_uses_a_non_system_test_user():
    config = _yaml(INSTALLER / "ci" / "autoinstall-ci.yaml")
    assert config["interactive-sections"] == []
    assert config["storage"]["layout"]["name"] == "direct"
    # "eira" is the daemons' system account created by the package.
    assert config["identity"]["username"] not in {"eira", "root"}
    assert config["shutdown"] == "poweroff"
    assert config["late-commands"] == _yaml(INSTALLER / "autoinstall.yaml")["late-commands"]


def _firstboot(tmp_path: Path, passwd: str) -> subprocess.CompletedProcess[str]:
    passwd_file = tmp_path / "passwd"
    passwd_file.write_text(passwd, encoding="utf-8")
    env = {
        **os.environ,
        "EIRA_FIRSTBOOT_DRY_RUN": "1",
        "EIRA_PASSWD_FILE": str(passwd_file),
        "EIRA_ACCOUNTS_DIR": str(tmp_path / "accounts"),
        "EIRA_FIRSTBOOT_STAMP": str(tmp_path / "firstboot.done"),
    }
    return subprocess.run(
        ["sh", str(INSTALLER / "eira-firstboot")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


PASSWD = (
    "root:x:0:0::/root:/bin/bash\n"
    "syslog:x:104:110::/home/syslog:/usr/sbin/nologin\n"
    "svc:x:1001:1001::/srv:/usr/sbin/nologin\n"
    "soren:x:1000:1000:Soren:/home/soren:/bin/bash\n"
    "nobody:x:65534:65534::/nonexistent:/usr/sbin/nologin\n"
)


def test_firstboot_makes_eira_the_default_session(tmp_path):
    result = _firstboot(tmp_path, PASSWD)
    assert result.returncode == 0, result.stderr
    account = (tmp_path / "accounts" / "soren").read_text(encoding="utf-8")
    assert "[User]" in account
    assert "Session=eira-session" in account


def test_firstboot_keeps_existing_accountsservice_settings(tmp_path):
    accounts = tmp_path / "accounts"
    accounts.mkdir()
    (accounts / "soren").write_text(
        "[User]\nLanguage=da_DK.UTF-8\nSession=ubuntu\nIcon=/home/soren/.face\n",
        encoding="utf-8",
    )
    result = _firstboot(tmp_path, PASSWD)
    assert result.returncode == 0, result.stderr
    account = (accounts / "soren").read_text(encoding="utf-8")
    assert "Language=da_DK.UTF-8" in account
    assert "Session=eira-session" in account
    assert "Session=ubuntu" not in account
    assert account.count("Session=") == 1


def test_firstboot_fails_without_a_human_user(tmp_path):
    result = _firstboot(tmp_path, "root:x:0:0::/root:/bin/bash\n")
    assert result.returncode != 0
    assert not (tmp_path / "accounts").exists() or not any((tmp_path / "accounts").iterdir())


def test_postinstall_uses_every_file_build_iso_stages():
    script = BUILD_ISO.read_text(encoding="utf-8")
    postinstall = (INSTALLER / "eira-postinstall.sh").read_text(encoding="utf-8")
    for staged in ("eira-os-core.deb", "eira-firstboot", "eira-firstboot.service"):
        assert f"$STAGE/eira/{staged}" in script
        assert f"$SRC/{staged}" in postinstall
    assert '"$SRC/ci/eira-ci-setup"' in postinstall
    assert '"$STAGE/eira/ci/eira-ci-setup"' in script


def _base_iso(tmp_path: Path) -> Path:
    base = tmp_path / "base"
    (base / "boot" / "grub").mkdir(parents=True)
    (base / "boot" / "grub" / "grub.cfg").write_text(
        "set timeout=30\n"
        'menuentry "Try or Install Ubuntu" {\n'
        "  linux /casper/vmlinuz  --- quiet splash\n"
        "  initrd /casper/initrd\n"
        "}\n"
        'menuentry "Ubuntu (safe graphics)" {\n'
        "  linux /casper/vmlinuz  nomodeset --- quiet splash\n"
        "}\n",
        encoding="utf-8",
    )
    iso = tmp_path / "ubuntu-26.04-desktop-amd64.iso"
    subprocess.run(
        ["xorriso", "-as", "mkisofs", "-quiet", "-o", str(iso), str(base)],
        check=True,
        capture_output=True,
    )
    return iso


def _build(tmp_path: Path, *extra: str) -> tuple[Path, str, str]:
    deb = tmp_path / "eira-os-core.deb"
    deb.write_bytes(b"not a real package")
    # A given eira-labwc package: building one needs meson and a toolchain.
    labwc = tmp_path / "eira-labwc.deb"
    labwc.write_bytes(b"not a real package")
    out = tmp_path / "out"
    result = subprocess.run(
        ["bash", str(BUILD_ISO), "--base-iso", str(_base_iso(tmp_path)),
         "--deb", str(deb), "--labwc-deb", str(labwc), "--output-dir", str(out), *extra],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    iso = next(out.glob("*.iso"))
    listing = subprocess.run(
        ["xorriso", "-indev", str(iso), "-find", "/", "-type", "f"],
        capture_output=True, text=True, check=True,
    ).stdout
    grub = tmp_path / "grub.cfg"
    subprocess.run(
        ["xorriso", "-osirrox", "on", "-indev", str(iso), "-extract", "/boot/grub/grub.cfg", str(grub)],
        check=True, capture_output=True,
    )
    autoinstall = tmp_path / "autoinstall.yaml"
    subprocess.run(
        ["xorriso", "-osirrox", "on", "-indev", str(iso), "-extract", "/autoinstall.yaml", str(autoinstall)],
        check=True, capture_output=True,
    )
    return iso, listing, grub.read_text(encoding="utf-8") + "\n#AUTOINSTALL\n" + autoinstall.read_text(encoding="utf-8")


needs_xorriso = pytest.mark.skipif(shutil.which("xorriso") is None, reason="xorriso not installed")


@needs_xorriso
def test_build_iso_remasters_a_base_iso(tmp_path):
    iso, listing, text = _build(tmp_path)
    grub, autoinstall = text.split("\n#AUTOINSTALL\n")
    assert iso.name == "EiraOS-1.0-RC1-amd64.iso"
    for path in ("/autoinstall.yaml", "/eira/eira-os-core.deb",
                 "/eira/eira-postinstall.sh", "/eira/eira-firstboot"):
        assert f"'{path}'" in listing
    # The real installer image must never carry the unattended CI test.
    assert "/eira/ci/" not in listing
    assert "interactive-sections: []" not in autoinstall
    assert 'menuentry "Installér EiraOS (Ubuntu 26.04 LTS)"' in grub
    assert 'menuentry "Ubuntu (safe graphics)"' in grub
    assert " autoinstall " not in grub
    assert (iso.parent / f"{iso.name}.sha3-256").read_text(encoding="utf-8").strip()


@needs_xorriso
def test_build_iso_ci_variant_is_unattended_and_separately_named(tmp_path):
    iso, listing, text = _build(tmp_path, "--ci-unattended")
    grub, autoinstall = text.split("\n#AUTOINSTALL\n")
    assert iso.name == "EiraOS-1.0-RC1-amd64-ci-unattended.iso"
    assert "'/eira/ci/eira-ci-report'" in listing
    assert "interactive-sections: []" in autoinstall
    assert "set timeout=1" in grub
    # Only the default entry boots straight into the unattended install.
    assert grub.count(" autoinstall console=tty0 console=ttyS0,115200 ---") == 1


def test_build_iso_requires_a_base_iso(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "EIRA_BASE_ISO"}
    result = subprocess.run(
        ["bash", str(BUILD_ISO), "--output-dir", str(tmp_path)],
        env=env, capture_output=True, text=True, check=False,
    )
    if shutil.which("xorriso") is None:
        assert result.returncode == 69
    else:
        assert result.returncode == 64
        assert "fetch_ubuntu_iso.sh" in result.stderr
