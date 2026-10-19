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


def test_eira_session_service_binds_to_eira_target():
    unit = _read("packaging/systemd/eira-session.service")
    assert "Wants=eira.target" in unit
    assert "After=eira.target graphical.target" in unit
    assert "User=ubuntu" in unit
    assert "NoNewPrivileges=true" in unit


def test_build_iso_installs_session_stack_and_enables_service():
    script = _read("scripts/build_iso.sh")
    assert "labwc" in script
    assert "greetd" in script
    assert "systemctl enable eira-session.service" in script
    assert "gdm3" not in script


def test_ubuntu_install_enables_eira_session_service():
    script = _read("packaging/ubuntu/install.sh")
    assert "labwc" in script
    assert "greetd" in script
    assert "systemctl enable eira-session.service" in script
    assert "gdm3" not in script
