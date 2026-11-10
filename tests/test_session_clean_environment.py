"""eira-session starts from known paths, never from the inherited environment.

GATE-KERNEL bilag A pkt. 1 ("Rest"): what the session starts, and where the
app finds the daemons, is decided by the package and by a root-owned
/etc/eira/eira.conf, not by the environment the session inherits. This does
not close "a program running as the user restarts the app with LD_PRELOAD";
that is the consent agent's job (specs/EIRA-CONSENT-AGENT-0.1.md).

The script is run for real, against a copy whose two fixed paths (PATH and
the conf file) point into a temp dir with a fake `labwc` that records its
environment. It refuses to run as root, so as root the test drops to nobody.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path():  # noqa: F811 - must be traversable by nobody when tests run as root
    import tempfile

    path = Path(tempfile.mkdtemp(prefix="eira-session-test-"))
    path.chmod(0o755)
    yield path
    shutil.rmtree(path, ignore_errors=True)

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "packaging" / "session" / "eira-session"
NOBODY = 65534


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    record = tmp_path / "labwc.env"
    fake_labwc = bindir / "labwc"
    fake_labwc.write_text(f'#!/bin/sh\n{{ echo "ARGS=$*"; env; }} > "{record}"\n')
    shell_bin = tmp_path / "eira-spatial-desktop"
    shell_bin.write_text("#!/bin/sh\n")
    for exe in (fake_labwc, shell_bin):
        exe.chmod(0o755)
    for tool in ("sh", "env", "sed", "stat", "id", "mkdir", "chmod"):
        found = shutil.which(tool)
        if found:
            (bindir / tool).symlink_to(found)

    conf = tmp_path / "eira.conf"
    text = SCRIPT.read_text(encoding="utf-8")
    assert "PATH=/usr/sbin:/usr/bin:/sbin:/bin\n" in text
    assert "EIRA_CONF=/etc/eira/eira.conf\n" in text
    text = text.replace("PATH=/usr/sbin:/usr/bin:/sbin:/bin\n", f"PATH={bindir}\n")
    text = text.replace("EIRA_CONF=/etc/eira/eira.conf\n", f"EIRA_CONF={conf}\n")
    text = text.replace("/usr/bin/eira-spatial-desktop", str(shell_bin))
    script = tmp_path / "eira-session"
    script.write_text(text)
    script.chmod(0o755)
    tmp_path.chmod(0o755)
    record.touch()
    record.chmod(0o666)
    return script, conf, record


def _run(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    cmd = [str(script)]
    if os.getuid() == 0:
        setpriv = shutil.which("setpriv")
        if setpriv is None:
            pytest.skip("running as root without setpriv")
        cmd = [setpriv, f"--reuid={NOBODY}", f"--regid={NOBODY}", "--clear-groups", *cmd]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)


def _recorded(record: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in record.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep:
            out[key] = value
    return out


HOSTILE = {
    "EIRA_SHELL_BIN": "/tmp/evil-shell",
    "EIRA_LABWC_CONFIG": "/home/user/.config/evil-labwc",
    "EIRA_SESSION_WM": "labwc",
    "EIRA_RUN_DIR": "/tmp/fake-daemons",
    "EIRA_SOCKET_DIR": "/tmp/fake-daemons",
    "LD_PRELOAD": "/tmp/inject.so",
    "LD_LIBRARY_PATH": "/tmp/libs",
    "GTK_MODULES": "evil",
    "WEBKIT_INJECTED_BUNDLE_PATH": "/tmp/bundle",
}


def test_inherited_overrides_are_ignored(tmp_path: Path) -> None:
    script, _conf, record = _setup(tmp_path)
    result = _run(script, {"HOME": "/nonexistent", **HOSTILE})
    assert result.returncode == 0, result.stderr
    env = _recorded(record)
    assert env["ARGS"] == "-C /usr/share/eira-os/labwc"
    assert env["EIRA_RUN_DIR"] == "/run/eira"
    for name in ("EIRA_SOCKET_DIR", "EIRA_SHELL_BIN", "EIRA_LABWC_CONFIG", "LD_PRELOAD",
                 "LD_LIBRARY_PATH", "GTK_MODULES", "WEBKIT_INJECTED_BUNDLE_PATH"):
        assert name not in env, name


def test_untrusted_conf_is_not_sourced(tmp_path: Path) -> None:
    """A conf the user (or anyone but root) owns or can write is ignored."""
    script, conf, record = _setup(tmp_path)
    conf.write_text("EIRA_LABWC_CONFIG=/home/user/.config/evil-labwc\nEIRA_RUN_DIR=/tmp/x\n")
    conf.chmod(0o666)
    result = _run(script, {"HOME": "/nonexistent"})
    assert result.returncode == 0, result.stderr
    assert "ignorerer" in result.stderr
    env = _recorded(record)
    assert env["ARGS"] == "-C /usr/share/eira-os/labwc"
    assert env["EIRA_RUN_DIR"] == "/run/eira"


def test_root_owned_conf_is_still_honoured(tmp_path: Path) -> None:
    """The administrator's conf keeps working (e.g. cage instead of labwc)."""
    if os.getuid() != 0:
        pytest.skip("needs root to create a root-owned conf")
    script, conf, record = _setup(tmp_path)
    conf.write_text("EIRA_RUN_DIR=/run/eira-alt\n")
    conf.chmod(0o644)
    result = _run(script, {"HOME": "/nonexistent"})
    assert result.returncode == 0, result.stderr
    assert _recorded(record)["EIRA_RUN_DIR"] == "/run/eira-alt"


def test_session_still_refuses_root() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'if [ "$(id -u)" = "0" ]' in text
