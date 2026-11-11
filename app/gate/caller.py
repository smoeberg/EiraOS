"""Who is on the other end of the socket (GATE-KERNEL bilag A pkt. 1).

The caller is never something the request says. The daemon server reads it
from the kernel (SO_PEERCRED) for every connection and hands it to the gate
handlers as `Caller`; a client cannot set or forge it.

- **The model** runs as its own system user, `eira-model`. Whatever it
  claims, its proposals have origin `model`, and it can never consent to or
  confirm anything: "the AI proposes, the gate decides".
- **A human** is any other uid. A session counts only if it was
  authenticated (claims verified at login) *for that uid*.

The gate kernel reads the caller from a context variable that the IPC layer
sets per request. Context variables are per thread and per task, so
concurrent requests never see each other's caller. No caller (anything that
did not come in over the socket) means no actor: the gate fails closed.
"""

from __future__ import annotations

import contextvars
import os
import pwd
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

MODEL_USER = os.environ.get("EIRA_MODEL_USER", "eira-model")


@dataclass(frozen=True)
class Caller:
    uid: int
    pid: int
    model: bool
    acting_as: str | None = None
    delegation_id: str | None = None
    # Effective gid at connect() (SO_PEERCRED). eira-consent means the setgid
    # consent agent (EIRA-CONSENT-AGENT §3).
    gid: int | None = None

    @property
    def consent_agent(self) -> bool:
        from app.gate.consent_path import is_consent_agent

        return is_consent_agent(self.gid)


CALLER: contextvars.ContextVar[Caller | None] = contextvars.ContextVar("gate_caller", default=None)


def model_identity(caller: Caller | None = None) -> str | None:
    caller = caller or CALLER.get()
    if caller is None or not caller.model:
        return None
    try:
        return f"model:{pwd.getpwuid(caller.uid).pw_name}"
    except KeyError:
        return f"model:uid:{caller.uid}"


def model_uid() -> int | None:
    try:
        return pwd.getpwnam(MODEL_USER).pw_uid
    except KeyError:
        return None  # no model user on this machine: nobody is the model


def from_peer(peer) -> Caller | None:
    """PeerCredentials (app.ipc.socket_security) → Caller."""
    if peer is None:
        return None
    return Caller(uid=peer.uid, pid=peer.pid, model=peer.uid == model_uid(), gid=getattr(peer, "gid", None))


class ModelIdentityMissing(RuntimeError):
    """An installed gate that cannot tell the model from a human must not run."""


def require_model_identity() -> int:
    """Fail closed where it matters. If `eira-model` is missing, model_uid()
    is None and the model would count as a human — able to consent. On an
    installed system (sockets under /run/eira) the gate therefore refuses to
    start; the reason is in the journal and systemd keeps retrying. The uid
    must also be a system uid and not the daemons' own (`eira`).
    """
    uid = model_uid()
    if uid is None:
        raise ModelIdentityMissing(f"system user {MODEL_USER!r} does not exist")
    if uid >= 1000:
        raise ModelIdentityMissing(f"{MODEL_USER!r} has uid {uid}, not a system uid")
    try:
        if uid == pwd.getpwnam("eira").pw_uid:
            raise ModelIdentityMissing(f"{MODEL_USER!r} shares the daemons' uid")
    except KeyError:
        pass
    return uid


def installed() -> bool:
    from app.ipc.paths import run_dir

    return str(run_dir()).rstrip("/") == "/run/eira"


@contextmanager
def acting_as(caller: Caller | None) -> Iterator[None]:
    token = CALLER.set(caller)
    try:
        yield
    finally:
        CALLER.reset(token)


def current() -> Caller | None:
    return CALLER.get()
