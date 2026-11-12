"""Access class per IPC method (UDVIKLINGSPLAN F0b, fundregister S-1, S-3).

Every method a daemon registers carries one class. The server refuses to
register a handler without one, so a new method cannot silently become a
write that any client may call. The classes say who may call and who checks:

- ``read``          No state change. Any client allowed on the socket.
- ``daemon_write``  Changes state. Only processes running as the daemon's own
                    service user (UID). The server checks this itself, from
                    SO_PEERCRED, before the handler runs.
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
from collections.abc import Callable
from enum import Enum
from typing import Any

Handler = Callable[[dict[str, Any]], Any]

ACCESS_DENIED = -32003


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


def daemon_write(handler: Handler) -> Handler:
    return _mark(handler, Access.DAEMON_WRITE)


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


def daemon_write_allowed(peer: Any) -> bool:
    """Only another daemon (same service user) may write. No peer means the
    request did not come over a socket with SO_PEERCRED: refuse."""
    uid = getattr(peer, "uid", None)
    return isinstance(uid, int) and uid == service_uid()
