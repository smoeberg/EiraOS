import grp
import os
import socket
import stat
import struct

import pytest

from app.ipc.socket_security import (
    PeerCredentialError,
    PeerCredentials,
    setup_unix_socket,
    socket_access_allowed,
    validate_peer_credentials,
)


class FakePeerSocket:
    def __init__(self, pid: int, uid: int, gid: int):
        self.credentials = struct.pack("3i", pid, uid, gid)

    def getsockopt(self, _level: int, _option: int, _length: int) -> bytes:
        return self.credentials


def test_setup_unix_socket_uses_mode_and_eira_group_or_dev_fallback(tmp_path):
    path = tmp_path / "eira.sock"
    old_path = tmp_path / "old.sock"
    old_path.write_text("stale socket path", encoding="utf-8")
    old_path.rename(path)

    try:
        eira_gid = grp.getgrnam("eira").gr_gid
    except KeyError:
        eira_gid = os.getgid()

    server = setup_unix_socket(str(path))
    try:
        details = path.stat()
        assert stat.S_ISSOCK(details.st_mode)
        assert stat.S_IMODE(details.st_mode) == 0o660
        # A non-root dev/CI process may not chown to eira, so current GID is
        # the documented fallback; privileged runs should get the target GID.
        expected_gid = (
            eira_gid
            if eira_gid == os.getgid() or os.geteuid() == 0
            else os.getgid()
        )
        assert details.st_gid == expected_gid
    finally:
        server.close()
        path.unlink(missing_ok=True)


def test_socket_mode_is_restored_after_chown_side_effect(tmp_path, monkeypatch):
    path = tmp_path / "mode-regression.sock"
    real_chown = os.chown

    def chown_then_degrade_mode(path_arg, uid, gid):
        real_chown(path_arg, uid, gid)
        # Simulate a runner/ownership operation that accidentally changes mode.
        os.chmod(path_arg, 0o600)

    monkeypatch.setattr(os, "chown", chown_then_degrade_mode)
    server = setup_unix_socket(str(path), mode=0o660, group="missing-eira-test-group")
    try:
        assert stat.S_IMODE(path.stat().st_mode) == 0o660
    finally:
        server.close()
        path.unlink(missing_ok=True)


def test_default_peer_validation_accepts_daemon_identity():
    peer = validate_peer_credentials(
        FakePeerSocket(os.getpid(), os.getuid(), os.getgid())
    )
    assert peer.uid == os.getuid()
    assert peer.gid == os.getgid()


def test_default_peer_validation_rejects_unlisted_uid_and_gid():
    fake_pid = 2_000_000_000  # No /proc entry, so no supplementary groups are added.
    fake = FakePeerSocket(fake_pid, 123_456, 123_457)
    with pytest.raises(PeerCredentialError, match="not authorized"):
        validate_peer_credentials(fake)


def test_explicit_allowlist_cannot_be_bypassed_by_current_uid():
    peer = PeerCredentials(pid=2_000_000_000, uid=os.getuid(), gid=os.getgid())
    assert not socket_access_allowed(
        peer,
        allowed_uids={123_456},
        allowed_gids={123_457},
    )
