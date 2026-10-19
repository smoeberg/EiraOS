from __future__ import annotations

import grp
import os
import signal
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.daemons.runner import start_daemons, stop_daemons


@pytest.fixture
def isolated_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run in an isolated socket directory and always clean up global daemons."""
    stop_daemons()
    socket_dir = tmp_path / "sockets"
    socket_dir.mkdir()
    monkeypatch.setenv("EIRA_RUN_DIR", str(socket_dir))
    yield socket_dir
    stop_daemons()


def test_socket_mode_is_0660(isolated_runner: Path) -> None:
    start_daemons("stated", isolated_runner)

    socket_file = isolated_runner / "stated.sock"
    info = socket_file.stat()

    assert stat.S_ISSOCK(info.st_mode)
    assert stat.S_IMODE(info.st_mode) == 0o660
    assert info.st_uid == os.getuid()

    # Minimal dev/CI images may not define the eira group; socket setup then
    # intentionally falls back to the runner's current GID (root's GID in dev).
    try:
        eira_gid = grp.getgrnam("eira").gr_gid
    except KeyError:
        eira_gid = os.getgid()
    assert info.st_gid == eira_gid


def test_sigterm_graceful_shutdown(tmp_path: Path) -> None:
    socket_dir = tmp_path / "subprocess-sockets"
    socket_dir.mkdir()
    socket_file = socket_dir / "stated.sock"
    env = os.environ.copy()
    env["EIRA_RUN_DIR"] = str(socket_dir)

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app.daemons.runner",
            "--daemon",
            "stated",
            "--socket-dir",
            str(socket_dir),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        deadline = time.monotonic() + 10
        while not socket_file.exists() and process.poll() is None:
            if time.monotonic() >= deadline:
                pytest.fail("runner did not create stated.sock within 10 seconds")
            time.sleep(0.05)

        assert socket_file.exists(), "runner exited before creating stated.sock"
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, f"runner failed to stop cleanly: {stdout}\n{stderr}"
        assert not socket_file.exists()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=3)
        if socket_file.exists():
            # Avoid leaving a stale test socket behind if an assertion fails.
            if stat.S_ISSOCK(socket_file.stat().st_mode):
                socket_file.unlink()


def test_unknown_daemon_rejected(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.daemons.runner",
            "--daemon",
            "xyz",
            "--socket-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    assert "invalid choice" in result.stderr
    assert "xyz" in result.stderr


def test_socket_dir_change_rejected_while_running(
    isolated_runner: Path, tmp_path: Path
) -> None:
    start_daemons("stated", isolated_runner)

    other_socket_dir = tmp_path / "other-sockets"
    other_socket_dir.mkdir()
    with pytest.raises(RuntimeError, match="Cannot change socket directory while daemons are running"):
        start_daemons("stated", other_socket_dir)
