from __future__ import annotations

import grp
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Generator
from pathlib import Path

import pytest

from app.daemons.runner import start_daemons, stop_daemons


@pytest.fixture
def isolated_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Path, None, None]:
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

    # Minimal dev/CI images may lack the eira group or permission to chown to it.
    # In that case socket setup falls back to the current GID (root's GID in dev).
    try:
        eira_gid = grp.getgrnam("eira").gr_gid
    except KeyError:
        eira_gid = os.getgid()
    assert info.st_gid in {eira_gid, os.getgid()}


def test_sigterm_graceful_shutdown(tmp_path: Path) -> None:
    # AF_UNIX socket paths are limited to ~108 bytes; use a short dir so the
    # test does not depend on the length of the pytest tmp_path.
    socket_dir = Path(tempfile.gettempdir()) / f"eira-t-{os.getpid()}"
    socket_dir.mkdir(exist_ok=True)
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
        assert process.returncode == 0, (
            f"runner failed to stop cleanly: {stdout}\\n{stderr}"
        )
        assert not socket_file.exists()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=3)
        if socket_file.exists() and stat.S_ISSOCK(socket_file.stat().st_mode):
            # Avoid leaving a stale test socket behind if an assertion fails.
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
    message = "Cannot change socket directory while daemons are running"
    with pytest.raises(RuntimeError, match=message):
        start_daemons("stated", other_socket_dir)
