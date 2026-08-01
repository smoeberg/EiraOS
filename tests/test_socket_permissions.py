from __future__ import annotations

import os
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from app.ipc.socket_security import (
    remove_unix_socket,
    resolve_group_gid,
    setup_unix_socket,
    socket_access_allowed,
)


def _unix_socket_runtime_available() -> bool:
    if sys.platform != "linux" or not hasattr(socket, "AF_UNIX"):
        return False
    try:
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    except (PermissionError, OSError):
        return False
    probe.close()
    return True


pytestmark = pytest.mark.skipif(
    not _unix_socket_runtime_available(),
    reason="runtime does not permit Linux Unix-domain socket syscalls",
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _wait_for(path: Path, *, exists: bool, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while path.exists() is not exists and time.monotonic() < deadline:
        time.sleep(0.05)
    assert path.exists() is exists


def test_socket_mode_permissions(tmp_path: Path) -> None:
    socket_path = tmp_path / "stated.sock"
    server = setup_unix_socket(str(socket_path))
    try:
        metadata = socket_path.stat()
        assert stat.S_ISSOCK(metadata.st_mode)
        assert stat.S_IMODE(metadata.st_mode) == 0o660
        assert metadata.st_gid in {
            os.getegid(),
            *os.getgroups(),
            resolve_group_gid("eira"),
        }
    finally:
        server.close()
        remove_unix_socket(str(socket_path))


def test_socket_cleanup_on_shutdown(tmp_path: Path) -> None:
    socket_path = tmp_path / "stated.sock"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPO_ROOT)
    environment["EIRA_STATE_DB"] = str(tmp_path / "eira_state.db")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app.daemons.runner",
            "--daemon",
            "stated",
            "--socket-dir",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for(socket_path, exists=True)
        assert stat.S_IMODE(socket_path.stat().st_mode) == 0o660
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, f"stdout={stdout}\nstderr={stderr}"
        _wait_for(socket_path, exists=False)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_unauthorized_user_access_blocked() -> None:
    socket_dir = Path(tempfile.mkdtemp(prefix="eira-socket-test-", dir="/tmp"))
    socket_dir.chmod(0o755)
    socket_path = socket_dir / "stated.sock"
    server = setup_unix_socket(str(socket_path))
    server.listen(1)
    try:
        metadata = socket_path.stat()
        untrusted_uid = metadata.st_uid + 100_000
        untrusted_gid = metadata.st_gid + 100_000
        assert not socket_access_allowed(
            str(socket_path), uid=untrusted_uid, gids={untrusted_gid}
        )

        if os.geteuid() == 0:
            import pwd

            nobody = pwd.getpwnam("nobody")

            def drop_privileges() -> None:
                os.setgroups([])
                os.setgid(nobody.pw_gid)
                os.setuid(nobody.pw_uid)

            client_code = (
                "import errno, socket, sys; "
                "s=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); "
                "\ntry: s.connect(sys.argv[1])"
                "\nexcept PermissionError as exc: raise SystemExit(0 if exc.errno == errno.EACCES else 2)"
                "\nexcept OSError as exc: raise SystemExit(0 if exc.errno == errno.EACCES else 3)"
                "\nraise SystemExit(1)"
            )
            result = subprocess.run(
                [sys.executable, "-c", client_code, str(socket_path)],
                check=False,
                preexec_fn=drop_privileges,
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert result.returncode == 0, result.stderr
    finally:
        server.close()
        remove_unix_socket(str(socket_path))
        socket_dir.rmdir()
