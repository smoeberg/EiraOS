"""Sprint 1: Wayland-session — labwc + greetd autologin (Fase 0)."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (REPO / rel).read_text()


def test_eira_session_uses_labwc_and_no_direct_gdm():
    script = _read("packaging/session/eira-session")
    assert "labwc" in script
    assert "gdm3" not in script
    assert "/usr/bin/eira-spatial-desktop" in script
    # No desktop, no start menu: session must not launch a full desktop stack
    assert "gnome-shell" not in script


def test_greetd_autologin_points_to_eira_session():
    cfg = _read("packaging/session/config/greetd/config.toml")
    assert 'command = "/usr/bin/eira-session"' in cfg
    assert "autologin = true" in cfg


def test_labwc_autostart_launches_eira_shell():
    autostart = _read("packaging/session/config/labwc/autostart")
    assert "eira-spatial-desktop" in autostart


def test_legacy_session_unit_is_not_shipped():
    # greetd owns the live user's session; a second systemd service would launch
    # a competing labwc process for the same account.
    assert not (REPO / "packaging" / "systemd" / "eira-session.service").exists()


def test_build_iso_installs_session_stack_and_enables_greetd():
    script = _read("scripts/build_iso.sh")
    assert "labwc" in script
    assert "greetd" in script
    assert "systemctl enable greetd.service" in script
    assert "systemctl enable eira-session.service" not in script
    assert "gdm3" not in script


def test_ubuntu_installer_uses_supported_deb_package():
    script = _read("packaging/ubuntu/install.sh")
    assert "scripts/build_deb.sh" in script
    assert 'apt-get install -y "$DEB_PATH"' in script
    assert "packaging/systemd/*.service" not in script
    assert "systemctl enable eira-session.service" not in script
    assert "walletd" not in script
    assert "presenced" not in script
    assert "contextd" not in script
