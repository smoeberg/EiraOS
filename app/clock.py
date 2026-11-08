"""Time the user cannot set back (GATE-KERNEL bilag A pkt. 6, RIGHTS-SET §4.1).

A consent is valid for a duration measured on CLOCK_BOOTTIME (monotonic,
counts suspend) within one boot. Wall-clock time is used for display and
audit only, never to decide whether a consent is still valid.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path

BOOT_ID_PATH = Path("/proc/sys/kernel/random/boot_id")
_CLOCK = getattr(time, "CLOCK_BOOTTIME", None)
# Without a kernel boot_id (non-Linux dev machines) the boot is "this
# process": a consent then dies with the daemon. Stricter, never looser.
_PROCESS_BOOT = "process:" + uuid.uuid4().hex


@dataclass(frozen=True)
class BootInstant:
    boot_id: str
    ns: int


def boot_now() -> BootInstant:
    try:
        boot_id = BOOT_ID_PATH.read_text(encoding="ascii").strip()
    except OSError:
        boot_id = ""
    if not boot_id or _CLOCK is None:
        return BootInstant(_PROCESS_BOOT, time.monotonic_ns())
    return BootInstant(boot_id, time.clock_gettime_ns(_CLOCK))


def within(started: BootInstant | None, now: BootInstant, duration_ns: int) -> bool:
    """True iff ``now`` is in the same boot and less than ``duration_ns`` later."""
    if started is None or started.boot_id != now.boot_id:
        return False
    elapsed = now.ns - started.ns
    return 0 <= elapsed < duration_ns
