"""Readiness and watchdog for a daemon run by systemd (UDVIKLINGSPLAN F1c.13,
vurderingen G-39).

``Restart=always`` restarts a daemon that dies, but not one that hangs. With
``Type=notify`` and ``WatchdogSec=`` in the unit, systemd expects ``READY=1``
when the daemon serves and ``WATCHDOG=1`` at least every WatchdogSec; when
the pings stop it kills and restarts the daemon.

The ping is not a timer. Before each one the runner calls ``health`` on the
daemon's own socket, through the real accept loop and request handling: a
daemon whose accept loop has ended or whose handling is stuck does not
answer, is not pinged for, and is restarted.

Nothing here runs unless systemd asks for it (NOTIFY_SOCKET, WATCHDOG_USEC),
so a development run and the units without ``Type=notify`` are unchanged.
"""

from __future__ import annotations

import logging
import os
import socket
from collections.abc import Callable, Iterable

from app.ipc.client import IpcClient

logger = logging.getLogger(__name__)

# How long the daemon may take to answer its own health call.
PROBE_TIMEOUT = 5.0
# Pings per watchdog period: two may be lost before systemd acts.
PINGS_PER_PERIOD = 3


def notify(state: str) -> bool:
    """Send one sd_notify(3) datagram. False if systemd did not ask for
    notifications or the datagram could not be sent; never raises."""
    address = os.environ.get("NOTIFY_SOCKET", "")
    if not address:
        return False
    if address.startswith("@"):  # abstract namespace
        address = "\0" + address[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM | socket.SOCK_CLOEXEC) as sock:
            sock.sendto(state.encode("ascii"), address)
    except OSError as exc:
        logger.warning("sd_notify %s failed: %s", state.split("=", 1)[0], exc)
        return False
    return True


def watchdog_interval() -> float | None:
    """Seconds between pings, or None when the unit has no WatchdogSec (or
    it is meant for another process: WATCHDOG_PID)."""
    raw = os.environ.get("WATCHDOG_USEC", "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        return None
    pid = os.environ.get("WATCHDOG_PID", "").strip()
    if pid and pid != str(os.getpid()):
        return None
    return int(raw) / 1_000_000 / PINGS_PER_PERIOD


def answers(daemon: str, timeout: float = PROBE_TIMEOUT) -> bool:
    """Whether the daemon answers ``health`` on its own socket."""
    try:
        reply = IpcClient(daemon, timeout=timeout).call("health")
    except Exception as exc:  # noqa: BLE001 - any failure is "does not answer"
        logger.warning("%s does not answer its health call: %s", daemon, exc)
        return False
    return isinstance(reply, dict) and reply.get("ok") is True


class ServiceNotifier:
    """What the runner tells systemd about the daemons it started."""

    def __init__(self, daemons: Iterable[str], probe: Callable[[str], bool] = answers) -> None:
        self.daemons = tuple(daemons)
        self._probe = probe
        self.interval = watchdog_interval()

    def ready(self) -> None:
        notify("READY=1")

    def stopping(self) -> None:
        notify("STOPPING=1")

    def healthy(self) -> bool:
        return bool(self.daemons) and all(self._probe(daemon) for daemon in self.daemons)

    def tick(self) -> bool:
        """One watchdog period: ping only if every daemon answers."""
        if self.interval is None:
            return False
        if not self.healthy():
            return False
        return notify("WATCHDOG=1")
