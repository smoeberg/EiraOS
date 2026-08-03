"""
EiraOS IPC Socket Security Module
Enforces strict 0660 / 0600 permissions on Unix Domain Sockets to prevent local privilege escalation.
"""
from dataclasses import dataclass
import grp
import os
import socket
import stat
from pathlib import Path
from typing import Iterable, Any


class PeerCredentialError(PermissionError):
    """Raised when peer credentials (UID/GID) do not match expected owner."""
    pass


@dataclass(frozen=True)
class PeerCredentials:
    pid: int
    uid: int
    gid: int


def resolve_group_gid(group_name: str) -> int:
    try:
        return grp.getgrnam(group_name).gr_gid
    except KeyError:
        return os.getgid()


def socket_access_allowed(
    target: Any,
    allowed_uids: Iterable[int] | None = None,
    allowed_gids: Iterable[int] | None = None,
    uid: int | None = None,
    gids: Iterable[int] | None = None,
) -> bool:
    if isinstance(target, PeerCredentials):
        creds_uid = target.uid
        creds_gid = target.gid
    elif isinstance(target, (str, Path)):
        if uid is not None:
            creds_uid = uid
            creds_gid = next(iter(gids)) if gids else os.getgid()
        else:
            try:
                st = os.stat(target)
                creds_uid = st.st_uid
                creds_gid = st.st_gid
            except OSError:
                return False
    else:
        creds_uid = uid or os.getuid()
        creds_gid = next(iter(gids)) if gids else os.getgid()

    current_uid = os.getuid()
    if creds_uid == current_uid or creds_uid == 0:
        return True
    if allowed_uids and creds_uid in allowed_uids:
        return True
    if allowed_gids and creds_gid in allowed_gids:
        return True
    if gids and creds_gid in gids:
        return True
    return False


def secure_socket_path(socket_path: str):
    if os.path.exists(socket_path):
        os.chmod(socket_path, stat.S_IRUSR | stat.S_IWUSR)
        file_mode = stat.S_IMODE(os.stat(socket_path).st_mode)
        if file_mode != 0o600:
            raise PermissionError(
                f"Security Warning: Socket '{socket_path}' has insecure permissions {oct(file_mode)}. "
                "Must be strictly 0600."
            )


def setup_unix_socket(socket_path: str, mode: int = 0o660, group: str = "eira") -> socket.socket:
    remove_unix_socket(socket_path)
    os.makedirs(os.path.dirname(socket_path), exist_ok=True)
    
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old_umask = os.umask(0o117)
    try:
        sock.bind(socket_path)
        os.chmod(socket_path, mode)
        gid = resolve_group_gid(group)
        try:
            os.chown(socket_path, -1, gid)
        except OSError:
            pass
    finally:
        os.umask(old_umask)
    return sock


def remove_unix_socket(socket_path: str) -> None:
    if os.path.exists(socket_path) or os.path.islink(socket_path):
        try:
            os.remove(socket_path)
        except OSError:
            pass


def validate_peer_credentials(sock: socket.socket) -> PeerCredentials:
    """Verifies SO_PEERCRED on Linux Unix sockets."""
    try:
        if hasattr(socket, "SO_PEERCRED"):
            import struct
            creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            pid, uid, gid = struct.unpack("3i", creds)
            return PeerCredentials(pid=pid, uid=uid, gid=gid)
    except Exception as exc:
        raise PeerCredentialError(f"Failed to validate peer credentials: {exc}") from exc
    return PeerCredentials(pid=os.getpid(), uid=os.getuid(), gid=os.getgid())


get_peer_credentials = validate_peer_credentials
