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


CALLER: contextvars.ContextVar[Caller | None] = contextvars.ContextVar("gate_caller", default=None)


def model_uid() -> int | None:
    try:
        return pwd.getpwnam(MODEL_USER).pw_uid
    except KeyError:
        return None  # no model user on this machine: nobody is the model


def from_peer(peer) -> Caller | None:
    """PeerCredentials (app.ipc.socket_security) → Caller."""
    if peer is None:
        return None
    return Caller(uid=peer.uid, pid=peer.pid, model=peer.uid == model_uid())


@contextmanager
def acting_as(caller: Caller | None) -> Iterator[None]:
    token = CALLER.set(caller)
    try:
        yield
    finally:
        CALLER.reset(token)


def current() -> Caller | None:
    return CALLER.get()
