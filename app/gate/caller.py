from __future__ import annotations
import contextvars, os, pwd
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator
MODEL_USER=os.environ.get("EIRA_MODEL_USER","eira-model")
@dataclass(frozen=True)
class Caller:
    uid:int; pid:int; model:bool; acting_as:str|None=None; delegation_id:str|None=None
CALLER:contextvars.ContextVar[Caller|None]=contextvars.ContextVar("gate_caller",default=None)
def model_uid():
    try:return pwd.getpwnam(MODEL_USER).pw_uid
    except KeyError:return None
def model_identity(caller=None):
    caller=caller or CALLER.get()
    if caller is None or not caller.model:return None
    try:return f"model:{pwd.getpwuid(caller.uid).pw_name}"
    except KeyError:return f"model:uid:{caller.uid}"
class ModelIdentityMissing(RuntimeError):pass
def require_model_identity():
    uid=model_uid()
    if uid is None:raise ModelIdentityMissing(f"system user {MODEL_USER!r} does not exist")
    if uid>=1000:raise ModelIdentityMissing(f"{MODEL_USER!r} has uid {uid}, not a system uid")
    try:
        if uid==pwd.getpwnam("eira").pw_uid:raise ModelIdentityMissing("model user shares daemon uid")
    except KeyError:pass
    return uid
def installed():
    from app.ipc.paths import run_dir
    return str(run_dir()).rstrip("/") == "/run/eira"
def from_peer(peer):
    if peer is None:return None
    return Caller(uid=peer.uid,pid=peer.pid,model=peer.uid==model_uid())
@contextmanager
def acting_as(caller):
    token=CALLER.set(caller)
    try:yield
    finally:CALLER.reset(token)
def current():return CALLER.get()
