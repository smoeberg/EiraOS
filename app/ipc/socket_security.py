"""EiraOS IPC socket security helpers."""

from __future__ import annotations

import grp
import logging
import os
import socket
import stat
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


class PeerCredentialError(PermissionError):
    """Raised when peer credentials (UID/GID) do not match the allowlist."""


@dataclass(frozen=True)
class PeerCredentials:
    pid: int
    uid: int
    gid: int


def resolve_group_gid(group_name: str) -> int | None:
    try:
        return grp.getgrnam(group_name).gr_gid
    except KeyError:
        logger.warning(
            "Unix group '%s' is unavailable; group-based socket permissions are disabled",
            group_name,
        )
        return None


def _supplementary_gids(pid: int) -> set[int]:
    try:
        with open(f"/proc/{pid}/status", encoding="ascii") as status:
            for line in status:
                if line.startswith("Groups:"):
                    return {int(gid) for gid in line.split()[1:]}
    except (OSError, ValueError):
        return set()
    return set()


def _parse_id_allowlist(env_name: str, default: set[int]) -> set[int]:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return default
    try:
        return {int(value.strip()) for value in raw.split(",") if value.strip()}
    except ValueError as exc:
        raise PeerCredentialError(f"{env_name} must be a comma-separated list of integers") from exc


def socket_access_allowed(
    target: Any,
    allowed_uids: Iterable[int] | None = None,
    allowed_gids: Iterable[int] | None = None,
    uid: int | None = None,
    gids: Iterable[int] | None = None,
) -> bool:
    if uid is not None:
        creds_uid = uid
        peer_gids = set(gids or ())
    elif isinstance(target, PeerCredentials):
        creds_uid = target.uid
        peer_gids = {target.gid, *_supplementary_gids(target.pid)}
    elif isinstance(target, (str, Path)):
        try:
            st = os.stat(target)
            creds_uid = st.st_uid
            peer_gids = {st.st_gid}
        except OSError:
            return False
    else:
        creds_uid = os.getuid()
        peer_gids = {os.getgid()}

    uid_allowlist = set(allowed_uids or ())
    gid_allowlist = set(allowed_gids or ())
    return creds_uid in uid_allowlist or bool(peer_gids.intersection(gid_allowlist))


def secure_socket_path(socket_path: str) -> None:
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
    if gid is None:
        logger.warning(
            "Continuing socket setup without group ownership enforcement for '%s'",
            group,
        )
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old_umask = os.umask(0o117)
    try:
        sock.bind(socket_path)
        os.chmod(socket_path, mode)
        if gid is not None:
            try:
                os.chown(socket_path, -1, gid)
            except PermissionError:
                logger.warning(
                    "Cannot chown socket '%s' to group gid %s; continuing without group ownership",
                    socket_path,
                    gid,
                )
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
    """Validate SO_PEERCRED against configured UID/GID allowlists (fail closed)."""
    if not hasattr(sock, "getsockopt") or not hasattr(socket, "SO_PEERCRED):
        raise PeerCredentialError("Peer credentials unavailable: SO_PEERCRED is required")
    try:
        creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        pid, uid, gid = struct.unpack("3i", creds)
        peer = PeerCredentials(pid=pid, uid=uid, gid=gid)
    except Exception as exc:
        raise PeerCredentialError(f"Failed to validate peer credentials: {exc}") from exc

    if allowed_uids is None:
        allowed_uids = _parse_id_allowlist("EIRA_IPC_ALLOWED_UIDS", {os.getuid()})
    if allowed_gids is None:
        default_gids = {os.getgid()}
        eira_gid = resolve_group_gid("eira")
        if eira_gid is not None:
            default_gids.add(eira_gid)
        allowed_gids = _parse_id_allowlist("EIRA_IPC_ALLOWED_GIDS", default_gids)

    if not socket_access_allowed(peer, allowed_uids=allowed_uids, allowed_gids=allowed_gids):
        raise PeerCredentialError(f"Peer UID {peer.uid} or GID {peer.gid} is not authorized")
    return peer


get_peer_credentials = validate_peer_credentials
