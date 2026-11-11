"""The consent agent's identity (EIRA-CONSENT-AGENT §3).

``eira-consent-agent`` is installed ``root:eira-consent 2755``. Running it
gives the process the effective GID ``eira-consent``, a group nobody is a
member of. The kernel then:

1. starts the dynamic loader in secure mode (``AT_SECURE``): ``LD_PRELOAD``
   and friends are ignored;
2. makes the process non-dumpable: no ptrace, no ``/proc/<pid>/mem``;
3. reports the effective GID on every socket it connects (``SO_PEERCRED``).

So a peer with ``gid == eira-consent`` is running the agent's code, and only
the kernel could have said so. That holds only if nobody else can get the
GID, which ``require_consent_path`` checks at start (fail closed, like
``require_model_identity``).
"""

from __future__ import annotations

import grp
import os
import pwd
import stat
from pathlib import Path

CONSENT_GROUP = os.environ.get("EIRA_CONSENT_GROUP", "eira-consent")
AGENT_PATH = Path(os.environ.get("EIRA_CONSENT_AGENT", "/usr/lib/eira-os/eira-consent-agent"))
GSHADOW = Path("/etc/gshadow")
# Groups the consent GID must never be shared with.
OTHER_GROUPS = ("eira", "eira-clients", "eira-model")


class ConsentPathBroken(RuntimeError):
    """The consent agent's GID could be held by someone else: an installed gate
    or identityd must not run."""


def consent_gid() -> int | None:
    try:
        return grp.getgrnam(CONSENT_GROUP).gr_gid
    except KeyError:
        return None


def is_consent_agent(peer_gid: int | None) -> bool:
    gid = consent_gid()
    return gid is not None and peer_gid == gid


def require_consent_path(gshadow: Path = GSHADOW, agent: Path = AGENT_PATH) -> int:
    """§3 preconditions. Raises ``ConsentPathBroken`` with the reason."""
    try:
        group = grp.getgrnam(CONSENT_GROUP)
    except KeyError:
        raise ConsentPathBroken(f"group {CONSENT_GROUP!r} does not exist") from None
    gid = group.gr_gid
    if gid >= 1000:
        raise ConsentPathBroken(f"{CONSENT_GROUP!r} has gid {gid}, not a system gid")
    for other in OTHER_GROUPS:
        try:
            if grp.getgrnam(other).gr_gid == gid:
                raise ConsentPathBroken(f"{CONSENT_GROUP!r} shares its gid with {other!r}")
        except KeyError:
            continue
    if group.gr_mem:
        raise ConsentPathBroken(f"{CONSENT_GROUP!r} has members: {', '.join(group.gr_mem)}")
    primary = [user.pw_name for user in pwd.getpwall() if user.pw_gid == gid]
    if primary:
        raise ConsentPathBroken(f"{CONSENT_GROUP!r} is the primary group of {', '.join(primary)}")
    # A group password would let newgrp/sg give a user process the GID.
    # /etc/gshadow is root-only: the daemons cannot read it, so postinst locks
    # the password and the VM test checks it; when readable it is checked here.
    try:
        for line in gshadow.read_text(encoding="utf-8").splitlines():
            fields = line.split(":")
            if fields[0] == CONSENT_GROUP and len(fields) > 1 and fields[1] not in ("!", "*", "!*", "!!"):
                raise ConsentPathBroken(f"{CONSENT_GROUP!r} has a group password")
    except (PermissionError, FileNotFoundError):
        pass
    try:
        info = agent.stat()
    except FileNotFoundError:
        raise ConsentPathBroken(f"{agent} is not installed") from None
    mode = stat.S_IMODE(info.st_mode)
    if info.st_uid != 0 or info.st_gid != gid or mode != 0o2755 or not stat.S_ISREG(info.st_mode):
        raise ConsentPathBroken(
            f"{agent} must be root:{CONSENT_GROUP} 2755 (is {info.st_uid}:{info.st_gid} {oct(mode)})"
        )
    return gid
