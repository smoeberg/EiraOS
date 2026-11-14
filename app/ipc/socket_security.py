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
    # Supplementary groups as the kernel recorded them at connect() time
    # (SO_PEERGROUPS). None means unknown; then /proc is consulted.
    groups: frozenset[int] | None = None
    # The peer's security label as the kernel recorded it at connect()
    # (SO_PEERSEC), e.g. "/usr/bin/eira-fleetd (enforce)". None if unknown.
    label: str | None = None


# Linux 4.13+: SO_PEERGROUPS returns the peer's supplementary GIDs from the
# credentials captured at connect(). Python does not export the constant.
SO_PEERGROUPS = getattr(socket, "SO_PEERGROUPS", 59)


def peer_groups(sock: Any) -> frozenset[int] | None:
    """Supplementary GIDs of a connected Unix peer, or None if unavailable."""
    size = 64 * 4
    for _ in range(4):
        try:
            raw = sock.getsockopt(socket.SOL_SOCKET, SO_PEERGROUPS, size)
        except OSError as exc:
            if exc.errno == 34:  # ERANGE: buffer too small
                size *= 4
                continue
            return None
        except Exception:
            return None
        count = len(raw) // 4
        return frozenset(struct.unpack(f"{count}I", raw[: count * 4]))
    return None


SO_PEERSEC = getattr(socket, "SO_PEERSEC", 31)


def peer_label(sock: Any) -> str | None:
    """The connected Unix peer's LSM label (AppArmor on Ubuntu), or None."""
    try:
        raw = sock.getsockopt(socket.SOL_SOCKET, SO_PEERSEC, 4096)
    except Exception:
        return None
    if not isinstance(raw, bytes):
        return None
    text = raw.split(b"\0", 1)[0].decode("utf-8", "replace").strip()
    return text or None


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
        extra = target.groups if target.groups is not None else _supplementary_gids(target.pid)
        peer_gids = {target.gid, *extra}
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

    # Root remains an explicitly privileged local peer, matching the platform's
    # established socket-security policy. All non-root peers must match the allowlist.
    if creds_uid == 0:
        return True

    if allowed_uids is None and allowed_gids is None:
        # Preserve the helper's historical convenience behavior for callers that
        # explicitly omit an allowlist. The server accept path always supplies
        # concrete defaults, so it never relies on this fallback.
        return creds_uid == os.getuid()

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


# Socket access group. The desktop user is a member of this group, never of
# "eira" (the daemons' own group, which owns their data): a user who may talk
# to the daemons must not be able to write the gate's state (ADR-0003,
# "substratet beskytter Eira-laget").
SOCKET_GROUP = "eira-clients"


def setup_unix_socket(
    socket_path: str, mode: int = 0o660, group: str = SOCKET_GROUP
) -> socket.socket:
    """Create a Unix socket with deterministic mode and group ownership.

    The target group is used when it exists and can be applied. Minimal
    development/CI environments fall back to the process's current GID.
    """
    target_gid = resolve_group_gid(group)
    if target_gid is None and _strict_socket_group(socket_path):
        # In an installed system a missing group is a broken substrate (or an
        # AppArmor profile that cannot read /etc/group), not a dev setup.
        # Checked before touching the filesystem.
        raise PermissionError(
            f"Socket group '{group}' cannot be resolved; refusing to create '{socket_path}'"
        )
    remove_unix_socket(socket_path)
    os.makedirs(os.path.dirname(socket_path) or ".", exist_ok=True)

    fallback_gid = os.getgid()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old_umask = os.umask(0o117)
    try:
        sock.bind(socket_path)
        if target_gid is not None:
            try:
                os.chown(socket_path, -1, target_gid)
            except PermissionError:
                if _strict_socket_group(socket_path):
                    raise
                # The socket is owned by this process, so assigning its current
                # group is the safe development/CI fallback.
                logger.warning(
                    "Cannot chown socket '%s' to group gid %s; falling back to gid %s",

                    socket_path,
                    target_gid,
                    fallback_gid,
                )
                os.chown(socket_path, -1, fallback_gid)
        # If the group does not exist, bind() already assigns the current GID;
        # no chown call is necessary in a minimal development/test environment.
        # chown can clear mode bits on some platforms. Apply permissions last
        # so runner-side ownership changes cannot degrade the socket mode.
        os.chmod(socket_path, mode)
    except OSError:
        remove_unix_socket(socket_path)
        sock.close()
        raise
    finally:
        os.umask(old_umask)
    return sock


def _strict_socket_group(socket_path: str = "") -> bool:
    """Installed daemons must not silently fall back to their own GID."""
    flag = os.environ.get("EIRA_STRICT_SOCKET_GROUP", "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return True
    if flag in {"0", "false", "no"}:
        return False
    return str(socket_path).startswith("/run/eira/")


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
    if not hasattr(sock, "getsockopt") or not hasattr(socket, "SO_PEERCRED"):
        raise PeerCredentialError("Peer credentials unavailable: SO_PEERCRED is required")
    try:
        creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        pid, uid, gid = struct.unpack("3i", creds)
        peer = PeerCredentials(
            pid=pid, uid=uid, gid=gid, groups=peer_groups(sock), label=peer_label(sock)
        )
    except Exception as exc:
        raise PeerCredentialError(f"Failed to validate peer credentials: {exc}") from exc

    if allowed_uids is None:
        allowed_uids = _parse_id_allowlist("EIRA_IPC_ALLOWED_UIDS", {os.getuid()})
    if allowed_gids is None:
        default_gids = {os.getgid()}
        for name in (SOCKET_GROUP, "eira"):
            gid = resolve_group_gid(name)
            if gid is not None:
                default_gids.add(gid)
        allowed_gids = _parse_id_allowlist("EIRA_IPC_ALLOWED_GIDS", default_gids)

    if not socket_access_allowed(peer, allowed_uids=allowed_uids, allowed_gids=allowed_gids):
        raise PeerCredentialError(f"Peer UID {peer.uid} or GID {peer.gid} is not authorized")
    return peer


get_peer_credentials = validate_peer_credentials
