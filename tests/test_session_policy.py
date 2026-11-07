"""Explorer has no escape hatch: only the EiraOS session is selectable at login.

Runs packaging/session/eira-session-policy against a fake session tree with a
stand-in dpkg-divert that performs the same rename the real one does.
"""

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "packaging" / "session" / "eira-session-policy"

FAKE_DIVERT = """#!/bin/sh
# Minimal dpkg-divert: --local --rename --divert TARGET (--add|--remove) PATH
target=""; action=""; path=""
while [ $# -gt 0 ]; do
    case "$1" in
        --divert) target=$2; shift ;;
        --add|--remove) action=$1; path=$2; shift ;;
    esac
    shift
done
echo "$action $path $target" >> "$(dirname "$0")/divert.log"
if [ "$action" = --add ] && [ -e "$path" ]; then mv "$path" "$target"; fi
if [ "$action" = --remove ] && [ -e "$target" ]; then mv "$target" "$path"; fi
"""


def _tree(tmp_path: Path):
    wayland = tmp_path / "wayland-sessions"
    xsess = tmp_path / "xsessions"
    wayland.mkdir()
    xsess.mkdir()
    for name in ("eira-session.desktop", "ubuntu.desktop", "ubuntu-wayland.desktop"):
        (wayland / name).write_text(name)
    (xsess / "ubuntu-xorg.desktop").write_text("x")
    divert = tmp_path / "dpkg-divert"
    divert.write_text(FAKE_DIVERT)
    divert.chmod(0o755)
    conf = tmp_path / "eira.conf"
    conf.write_text("EIRA_IPC_TOKEN=x\n")
    env = {
        **os.environ,
        "EIRA_CONF": str(conf),
        "EIRA_HIDDEN_SESSIONS": str(tmp_path / "hidden"),
        "EIRA_SESSION_DIRS": f"{wayland} {xsess}",
        "EIRA_DPKG_DIVERT": str(divert),
    }
    return wayland, xsess, conf, env


def _run(env):
    return subprocess.run(["sh", str(SCRIPT)], env=env, check=True, capture_output=True, text=True)


def test_only_the_eira_session_remains_selectable(tmp_path):
    wayland, xsess, _conf, env = _tree(tmp_path)
    _run(env)
    assert sorted(p.name for p in wayland.iterdir()) == ["eira-session.desktop"]
    assert list(xsess.iterdir()) == []
    hidden = sorted(p.name for p in (tmp_path / "hidden").iterdir())
    assert hidden == [
        "wayland-sessions--ubuntu-wayland.desktop",
        "wayland-sessions--ubuntu.desktop",
        "xsessions--ubuntu-xorg.desktop",
    ]


def test_policy_is_idempotent_and_catches_new_sessions(tmp_path):
    wayland, _xsess, _conf, env = _tree(tmp_path)
    _run(env)
    _run(env)
    # A later package update installs another desktop session.
    (wayland / "gnome.desktop").write_text("g")
    _run(env)
    assert sorted(p.name for p in wayland.iterdir()) == ["eira-session.desktop"]


def test_it_policy_can_restore_the_ubuntu_sessions(tmp_path):
    wayland, xsess, conf, env = _tree(tmp_path)
    _run(env)
    conf.write_text("EIRA_IPC_TOKEN=x\nEIRA_ALLOW_UBUNTU_SESSION=1\n")
    _run(env)
    assert sorted(p.name for p in wayland.iterdir()) == [
        "eira-session.desktop",
        "ubuntu-wayland.desktop",
        "ubuntu.desktop",
    ]
    assert [p.name for p in xsess.iterdir()] == ["ubuntu-xorg.desktop"]


def test_a_client_cannot_enable_ubuntu_sessions_with_a_lookalike_line(tmp_path):
    wayland, _xsess, conf, env = _tree(tmp_path)
    conf.write_text("#EIRA_ALLOW_UBUNTU_SESSION=1\nEIRA_ALLOW_UBUNTU_SESSION=1 # no\n")
    _run(env)
    assert sorted(p.name for p in wayland.iterdir()) == ["eira-session.desktop"]


def test_package_installs_and_runs_the_policy():
    rules = (REPO / "packaging" / "debian" / "rules").read_text()
    postinst = (REPO / "packaging" / "debian" / "postinst").read_text()
    postrm = (REPO / "packaging" / "debian" / "postrm").read_text()
    unit = (REPO / "packaging" / "session" / "eira-session-policy.service").read_text()
    assert "usr/lib/eira/eira-session-policy" in rules
    assert "eira-session-policy.service" in rules
    assert "/usr/lib/eira/eira-session-policy" in postinst
    assert "--remove" in postrm
    assert "Before=display-manager.service" in unit
    control = (REPO / "packaging" / "debian" / "control").read_text()
    depends = control.split("\nDepends:", 1)[1].split("Recommends:", 1)[0]
    assert "gnome" not in depends and "gdm" not in depends
