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

import app.ipc.socket_security as socket_security
from app.ipc.socket_security import (
    PeerCredentials,
    remove_unix_socket,
    resolve_group_gid,
    secure_socket_path,
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


def _eira_group_available() -> bool:
    try:
        resolve_group_gid("eira-clients")
    except RuntimeError:
        return False
    return True


def test_socket_mode_permissions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    socket_path = tmp_path / "stated.sock"
    monkeypatch.setattr(socket_security.os, "chown", lambda *_args: None)
    server = setup_unix_socket(str(socket_path), group="root")
    try:
        metadata = socket_path.stat()
        assert stat.S_ISSOCK(metadata.st_mode)
        assert stat.S_IMODE(metadata.st_mode) == 0o660
    finally:
        server.close()
        remove_unix_socket(str(socket_path))


def test_secure_socket_path_verifies_before_chmod(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket_path = tmp_path / "stated.sock"
    socket_path.write_text("placeholder", encoding="utf-8")
    socket_path.chmod(0o644)
    chmod_calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(socket_security.os, "chmod", lambda *args: chmod_calls.append(args))

    with pytest.raises(PermissionError, match="strictly 0600"):
        secure_socket_path(str(socket_path))

    assert chmod_calls == []


def test_missing_group_disables_group_enforcement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing_group(_name: str) -> object:
        raise KeyError("eira")

    chown_calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(socket_security.grp, "getgrnam", missing_group)
    monkeypatch.setattr(socket_security.os, "chown", lambda *args: chown_calls.append(args))

    socket_path = tmp_path / "stated.sock"
    server = setup_unix_socket(str(socket_path))

    try:
        assert stat.S_IMODE(socket_path.stat().st_mode) == 0o660
        assert chown_calls == []
    finally:
        server.close()
        remove_unix_socket(str(socket_path))


def test_chown_failure_is_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied_chown(*_args: object) -> None:
        raise OSError("chown denied")

    monkeypatch.setattr(socket_security.os, "chown", denied_chown)

    with pytest.raises(OSError, match="chown denied"):
        setup_unix_socket(str(tmp_path / "stated.sock"), group="root")

    assert not (tmp_path / "stated.sock").exists()


def test_supplementary_gid_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket_security, "_supplementary_gids", lambda _pid: {4242})
    peer = PeerCredentials(pid=123, uid=os.getuid() + 1, gid=os.getgid() + 1)

    assert socket_access_allowed(peer, allowed_gids={4242})


def test_root_is_explicitly_allowed() -> None:
    peer = PeerCredentials(pid=1, uid=0, gid=0)

    assert socket_access_allowed(peer, allowed_uids={999999}, allowed_gids={999999})


def test_socket_cleanup_on_shutdown(tmp_path: Path) -> None:
    if not _eira_group_available():
        pytest.skip("EiraOS integration sockets require the configured 'eira-clients' Unix group")

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


def test_unauthorized_user_access_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    eira_gid = resolve_group_gid("eira-clients")
    if eira_gid is None:
        pytest.skip("Socket authorization integration requires the configured 'eira-clients' Unix group")

    monkeypatch.setattr(socket_security.os, "chown", lambda *_args: None)
    socket_dir = Path(tempfile.mkdtemp(prefix="eira-socket-test-", dir="/tmp"))
    socket_dir.chmod(0o755)
    socket_path = socket_dir / "stated.sock"
    server = setup_unix_socket(str(socket_path), group="eira-clients")
    server.listen(1)
    try:
        metadata = socket_path.stat()
        # Model a peer that is neither the socket owner nor a member of eira.
        untrusted_uid = max(os.getuid(), metadata.st_uid) + 100_000
        untrusted_gid = eira_gid + 100_000
        assert not socket_access_allowed(
            str(socket_path),
            allowed_uids={metadata.st_uid},
            allowed_gids={eira_gid},
            uid=untrusted_uid,
            gids={untrusted_gid},
        )

        # Where the test process has the privilege, also verify the kernel's
        # filesystem permission layer rejects a real connection from nobody.
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


def test_peer_groups_come_from_kernel_snapshot(tmp_path):
    """SO_PEERGROUPS gives the connecting process's supplementary groups
    without reading /proc (which AppArmor confines to the daemon's own pid)."""
    import os
    import socket as _socket

    a, b = _socket.socketpair(_socket.AF_UNIX, _socket.SOCK_STREAM)
    try:
        groups = socket_security.peer_groups(a)
        assert groups is not None
        assert groups == frozenset(os.getgroups()) or set(os.getgroups()) <= groups
        creds = socket_security.validate_peer_credentials(
            a, allowed_uids=set(), allowed_gids={os.getgid()}
        )
        assert creds.groups == groups
    finally:
        a.close()
        b.close()


def test_supplementary_group_admits_peer_without_proc(monkeypatch):
    monkeypatch.setattr(
        socket_security, "_supplementary_gids", lambda _pid: (_ for _ in ()).throw(AssertionError)
    )
    peer = socket_security.PeerCredentials(pid=1, uid=1000, gid=1000, groups=frozenset({4242}))
    assert socket_security.socket_access_allowed(peer, allowed_uids=set(), allowed_gids={4242})


def test_installed_socket_refuses_silent_gid_fallback(monkeypatch):
    monkeypatch.setattr(socket_security, "resolve_group_gid", lambda _name: None)
    monkeypatch.delenv("EIRA_STRICT_SOCKET_GROUP", raising=False)
    with pytest.raises(PermissionError, match="cannot be resolved"):
        socket_security.setup_unix_socket("/run/eira/test-strict.sock")


def test_dev_socket_keeps_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(socket_security, "resolve_group_gid", lambda _name: None)
    monkeypatch.delenv("EIRA_STRICT_SOCKET_GROUP", raising=False)
    sock = socket_security.setup_unix_socket(str(tmp_path / "dev.sock"))
    sock.close()


def test_all_daemon_apparmor_profiles_can_resolve_groups():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "packaging" / "apparmor"
    profiles = sorted(root.glob("usr.bin.eira-*"))
    assert profiles
    for profile in profiles:
        assert "abstractions/nameservice" in profile.read_text(), profile.name
