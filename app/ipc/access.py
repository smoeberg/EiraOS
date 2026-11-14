"""Access class per IPC method (UDVIKLINGSPLAN F0b, fundregister S-1, S-3).

Every method a daemon registers carries one class. The server refuses to
register a handler without one, so a new method cannot silently become a
write that any client may call. The classes say who may call and who checks:

- ``read``          No state change. Any client allowed on the socket.
- ``daemon_write``  Changes state. Only the named daemons that need it
                    (``callers``), running as the service user. The server
                    checks both before the handler runs: the UID from
                    SO_PEERCRED and which daemon the caller is, from the
                    kernel (its AppArmor label, else its systemd unit's
                    cgroup). Same UID is not enough (UDVIKLINGSPLAN F1c.3,
                    vurderingen G-3).
- ``caller``        The handler decides from the kernel caller (SO_PEERCRED):
                    the gate, login, the consent agent, delegation, Fleet
                    administration, the model. It must therefore receive the
                    caller (``wants_peer``).
- ``signed``        The handler verifies a cryptographic proof carried in the
                    request (a device signature, a pairing token).
- ``refused``       Always rejects (old paths that must go through the gate).
- ``open_write``    Changes state with no caller or proof check. Allowed only
                    for the known gaps listed with a plan id in
                    tests/test_ipc_access.py; the list may only shrink.

The socket group (``eira-clients``) and the optional IPC token are not an
authorization boundary against the desktop user: the user is in that group
and may read the token. These classes are.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from enum import Enum
from pathlib import Path
from typing import Any

Handler = Callable[[dict[str, Any]], Any]

ACCESS_DENIED = -32003

# The daemons that may be named as callers of a ``daemon_write`` method. Each
# runs from /usr/bin/eira-<name> under the AppArmor profile of that name and in
# the systemd unit eira-<name>.service.
DAEMONS = frozenset(
    {"stated", "identityd", "fleetd", "veritasd", "intentd", "graphd", "delegationd"}
)


class Access(str, Enum):
    READ = "read"
    DAEMON_WRITE = "daemon_write"
    CALLER = "caller"
    SIGNED = "signed"
    REFUSED = "refused"
    OPEN_WRITE = "open_write"


def _mark(handler: Handler, kind: Access, note: str | None = None) -> Handler:
    wants_peer = bool(getattr(handler, "wants_peer", False))
    if kind is Access.CALLER and not wants_peer:
        raise TypeError("a 'caller' method must receive the kernel caller (wants_peer)")

    def wrapped(params: dict[str, Any]) -> Any:
        return handler(params)

    wrapped.access = kind  # type: ignore[attr-defined]
    wrapped.access_note = note  # type: ignore[attr-defined]
    wrapped.wants_peer = wants_peer  # type: ignore[attr-defined]
    wrapped.__wrapped__ = handler  # type: ignore[attr-defined]
    wrapped.__doc__ = getattr(handler, "__doc__", None)
    return wrapped


def read(handler: Handler) -> Handler:
    return _mark(handler, Access.READ)


def daemon_write(handler: Handler, callers: Iterable[str]) -> Handler:
    """A write only the named daemons may make. ``callers`` are daemon names
    (``"fleetd"``); an empty list means no daemon calls it today, so every
    caller is refused until one is named here."""
    if isinstance(callers, str):
        raise TypeError("callers must be a list of daemon names, not one string")
    names = frozenset(callers)
    unknown = names - DAEMONS
    if unknown:
        raise ValueError(f"unknown daemon(s) in callers: {sorted(unknown)}")
    note = "Kun " + ", ".join(sorted(names)) if names else "Ingen daemon kalder den endnu"
    wrapped = _mark(handler, Access.DAEMON_WRITE, note)
    wrapped.callers = names  # type: ignore[attr-defined]
    return wrapped


def caller(handler: Handler) -> Handler:
    return _mark(handler, Access.CALLER)


def signed(handler: Handler) -> Handler:
    return _mark(handler, Access.SIGNED)


def refused(handler: Handler) -> Handler:
    return _mark(handler, Access.REFUSED)


def open_write(handler: Handler, plan: str) -> Handler:
    """A known gap: a client-callable write without a check. ``plan`` names
    the plan item that closes it (e.g. "F1.5")."""
    if not plan:
        raise ValueError("an open_write method must name the plan item that closes it")
    return _mark(handler, Access.OPEN_WRITE, plan)


def access_of(handler: Handler) -> Access | None:
    kind = getattr(handler, "access", None)
    return kind if isinstance(kind, Access) else None


def service_uid() -> int:
    """The UID the daemons run as. A ``daemon_write`` caller must have it."""
    return os.getuid()


def callers_of(handler: Handler) -> frozenset[str]:
    return frozenset(getattr(handler, "callers", frozenset()))


_LABEL = re.compile(r"^/usr/bin/eira-([a-z]+)$")
_UNIT = re.compile(r"/eira-([a-z]+)\.service$")


def daemon_from_label(label: str | None) -> str | None:
    """``/usr/bin/eira-fleetd (enforce)`` -> ``fleetd``. Only enforced
    profiles count: a profile in complain mode confines nothing."""
    if not label:
        return None
    name, _, mode = label.strip().rpartition(" ")
    if mode != "(enforce)":
        return None
    # A stack with "unconfined" (X//&unconfined, what a profile change from
    # an unconfined task can give) is confined exactly by X. Any other stack
    # is not one daemon.
    parts = [part for part in name.split("//&") if part != "unconfined"]
    if len(parts) != 1:
        return None
    match = _LABEL.match(parts[0])
    return match.group(1) if match and match.group(1) in DAEMONS else None


def label_is_confined(label: str | None) -> bool:
    """Whether the kernel put the caller under some AppArmor profile. Then
    the label alone decides; a confined process cannot fall back to its
    cgroup (rights-sync runs under its own profile, not a daemon's)."""
    if not label:
        return False
    return label.strip() not in {"unconfined", ""}


def daemon_from_cgroup(pid: int | None, proc: Path = Path("/proc")) -> str | None:
    """The daemon whose systemd unit the caller runs in (cgroup v2). The
    cgroup tree is root's: a process cannot move itself into another unit."""
    if not isinstance(pid, int) or pid <= 0:
        return None
    try:
        text = (proc / str(pid) / "cgroup").read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError):
        return None
    for line in text.splitlines():
        hierarchy, _, path = line.partition("::")
        if hierarchy != "0":
            continue
        match = _UNIT.search(path.strip())
        if match and match.group(1) in DAEMONS:
            return match.group(1)
    return None


def peer_daemon(peer: Any) -> str | None:
    """Which EiraOS daemon the kernel says the caller is, or None."""
    label = getattr(peer, "label", None)
    if label_is_confined(label):
        return daemon_from_label(label)
    return daemon_from_cgroup(getattr(peer, "pid", None))


def strict_daemon_identity() -> bool:
    """On an installed system (sockets in /run/eira) the caller must be a
    named daemon. A development run has no profiles or units; there the
    service UID is still required, but any process with it counts."""
    flag = os.environ.get("EIRA_STRICT_DAEMON_IDENTITY", "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return True
    if flag in {"0", "false", "no"}:
        return False
    from app.ipc.paths import run_dir

    return str(run_dir()).rstrip("/") == "/run/eira"


def daemon_write_allowed(peer: Any, callers: Iterable[str] = ()) -> bool:
    """Only a named daemon, running as the service user, may write. No peer
    means the request did not come over a socket with SO_PEERCRED: refuse.

    Both checks are needed: the desktop user can put itself under a daemon's
    AppArmor profile (an unconfined process may change profile), but cannot
    take the service UID; and a process with the service UID is not
    necessarily a daemon (rights-sync, anything root starts as eira)."""
    uid = getattr(peer, "uid", None)
    if not (isinstance(uid, int) and uid == service_uid()):
        return False
    name = peer_daemon(peer)
    if name is not None:
        return name in frozenset(callers)
    return not strict_daemon_identity()
