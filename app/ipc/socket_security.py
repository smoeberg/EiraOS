from __future__ import annotations

import os
import socket
import stat
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import grp
except ImportError:  # pragma: no cover - unavailable on Windows
    grp = None  # type: ignore[assignment]

DEFAULT_SOCKET_MODE = 0o660
SO_PEERCRED_STRUCT = struct.Struct("3i")


@dataclass(frozen=True)
class PeerCredentials:
    pid: int
    uid: int
    gid: int


class PeerCredentialError(PermissionError):
    """Raised when a Unix socket peer is outside the allowed UID/GID set."""


def resolve_group_gid(group: str) -> int:
    """Resolve a group name, falling back to the process GID for dev/test."""
    if grp is not None:
        try:
            return grp.getgrnam(group).gr_gid
        except KeyError:
            pass
    return os.getegid() if hasattr(os, "getegid") else 0


def _remove_stale_socket(path: Path) -> None:
    try:
        file_mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(file_mode):
        raise FileExistsError(f"Refusing to replace non-socket path: {path}")
    path.unlink()


def _set_socket_group(path: Path, group: str) -> int:
    desired_gid = resolve_group_gid(group)
    try:
        os.chown(path, -1, desired_gid)
        return desired_gid
    except PermissionError:
        fallback_gid = os.getegid()
        if desired_gid != fallback_gid:
            os.chown(path, -1, fallback_gid)
        return fallback_gid


def setup_unix_socket(
    socket_path: str, mode: int = DEFAULT_SOCKET_MODE, group: str = "eira"
) -> socket.socket:
    """Create and bind a least-privilege Unix stream socket.

    The process umask is restored immediately after bind. Call this during
    single-threaded server startup because umask is process-global.
    """
    if not hasattr(socket, "AF_UNIX"):
        raise NotImplementedError("Unix domain sockets are not supported")
    if mode & 0o007:
        raise ValueError("Unix socket mode must not grant access to others")

    path = Path(socket_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _remove_stale_socket(path)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    previous_umask = os.umask(0o117)
    try:
        server.bind(str(path))
    except BaseException:
        server.close()
        _remove_stale_socket(path)
        raise
    finally:
        os.umask(previous_umask)

    try:
        _set_socket_group(path, group)
        os.chmod(path, mode)
    except BaseException:
        server.close()
        _remove_stale_socket(path)
        raise
    return server


def remove_unix_socket(socket_path: str) -> None:
    """Remove a socket path without deleting unrelated filesystem objects."""
    _remove_stale_socket(Path(socket_path))


def get_peer_credentials(conn: socket.socket) -> PeerCredentials | None:
    """Return Linux SO_PEERCRED data, or None on unsupported platforms."""
    if sys.platform != "linux" or not hasattr(socket, "SO_PEERCRED"):
        return None
    raw = conn.getsockopt(
        socket.SOL_SOCKET, socket.SO_PEERCRED, SO_PEERCRED_STRUCT.size
    )
    return PeerCredentials(*SO_PEERCRED_STRUCT.unpack(raw))


def _supplementary_gids(pid: int) -> set[int]:
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return set()
    for line in status.splitlines():
        if line.startswith("Groups:"):
            return {int(value) for value in line.split(":", 1)[1].split()}
    return set()


def validate_peer_credentials(
    conn: socket.socket,
    *,
    allowed_uids: Iterable[int] | None = None,
    allowed_gids: Iterable[int] | None = None,
) -> PeerCredentials | None:
    """Validate a connected peer against allowed Linux user/group IDs."""
    credentials = get_peer_credentials(conn)
    if credentials is None:
        return None

    uid_set = set(allowed_uids) if allowed_uids is not None else {0, os.geteuid()}
    gid_set = set(allowed_gids) if allowed_gids is not None else {
        os.getegid(),
        resolve_group_gid("eira"),
    }
    peer_gids = {credentials.gid} | _supplementary_gids(credentials.pid)
    if credentials.uid in uid_set or peer_gids & gid_set:
        return credentials
    raise PeerCredentialError(
        f"Unauthorized Unix socket peer: uid={credentials.uid}, gid={credentials.gid}"
    )


def socket_access_allowed(
    socket_path: str, *, uid: int, gids: Iterable[int], write: bool = True
) -> bool:
    """Evaluate the POSIX permission class used for a socket connection."""
    if uid == 0:
        return True
    metadata = os.stat(socket_path)
    if uid == metadata.st_uid:
        bits = (metadata.st_mode >> 6) & 0o7
    elif metadata.st_gid in set(gids):
        bits = (metadata.st_mode >> 3) & 0o7
    else:
        bits = metadata.st_mode & 0o7
    required = 0o2 if write else 0o4
    return bool(bits & required)
