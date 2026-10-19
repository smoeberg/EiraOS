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
    except KeyError as exc:
        raise RuntimeError(f"Required Unix group '{group_name}' does not exist") from exc


def _supplementary_gids(pid: int) -> set[int]:
    try:
        with open(f"/proc/{pid}/status", encoding="ascii") as status:
            for line in status:
                if line.startswith("Groups:"):
                    return {int(gid) for gid in line.split()[1:]}
    except (OSError, ValueError):
        return set()
    return set()


def socket_access_allowed(
    target: Any,
    allowed_uids: Iterable[int] | None = None,
    allowed_gids: Iterable[int] | None = None,
    uid: int | None = None,
    gids: Iterable[int] | None = None,
) -> bool:
    current_uid = os.getuid()
    if uid is not None:
        creds_uid = uid
        peer_gids = set(gids or ())
        creds_gid = next(iter(peer_gids), os.getgid())
        peer_gids.add(creds_gid)
    elif isinstance(target, PeerCredentials):
        creds_uid = target.uid
        creds_gid = target.gid
        peer_gids = {creds_gid, *_supplementary_gids(target.pid)}
    elif isinstance(target, (str, Path)):
        try:
            st = os.stat(target)
            creds_uid = st.st_uid
            creds_gid = st.st_gid
        except OSError:
            return False
        peer_gids = {creds_gid}
    else:
        creds_uid = current_uid
        creds_gid = os.getgid()
        peer_gids = {creds_gid}

    if allowed_uids and creds_uid in allowed_uids:
        return True
    if allowed_gids and peer_gids.intersection(allowed_gids):
        return True
    if creds_uid == 0:
        return True
    return creds_uid == current_uid


def secure_socket_path(socket_path: str):
    if os.path.exists(socket_path):
        file_mode = stat.S_IMODE(os.stat(socket_path).st_mode)
        if file_mode != 0o600:
            raise PermissionError(
                f"Security Warning: Socket '{socket_path}' has insecure permissions {oct(file_mode)}. "
                "Must be strictly 0600."
            )
        os.chmod(socket_path, stat.S_IRUSR | stat.S_IWUSR)


def setup_unix_socket(socket_path: str, mode: int = 0o660, group: str = "eira") -> socket.socket:
    remove_unix_socket(socket_path)
    os.makedirs(os.path.dirname(socket_path), exist_ok=True)

    gid = resolve_group_gid(group)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old_umask = os.umask(0o117)
    try:
        sock.bind(socket_path)
        os.chmod(socket_path, mode)
        os.chown(socket_path, -1, gid)
    except OSError:
        remove_unix_socket(socket_path)
        sock.close()
        raise
    finally:
        os.umask(old_umask)
    return sock


def remove_unix_socket(socket_path: str) -> None:
    if os.path.exists(socket_path) or os.path.islink(socket_path):
        try:
            os.remove(socket_path)
        except OSError:
            pass


def validate_peer_credentials(
    sock: Any,
    allowed_uids: Iterable[int] | None = None,
    allowed_gids: Iterable[int] | None = None,
) -> PeerCredentials:
    """Verifies SO_PEERCRED on Linux Unix sockets."""
    if hasattr(sock, "getsockopt") and hasattr(socket, "SO_PEERCRED"):
        try:
            import struct
            creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            pid, uid, gid = struct.unpack("3i", creds)
            peer = PeerCredentials(pid=pid, uid=uid, gid=gid)
        except Exception as exc:
            raise PeerCredentialError(f"Failed to validate peer credentials: {exc}") from exc
    else:
        peer = PeerCredentials(pid=os.getpid(), uid=os.getuid(), gid=os.getgid())

    if allowed_uids is not None or allowed_gids is not None:
        if not socket_access_allowed(peer, allowed_uids=allowed_uids, allowed_gids=allowed_gids):
            raise PeerCredentialError(f"Peer UID {peer.uid} or GID {peer.gid} is not authorized")

    return peer


get_peer_credentials = validate_peer_credentials
