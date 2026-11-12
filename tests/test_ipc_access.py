"""Access class per IPC method (UDVIKLINGSPLAN F0b; fundregister S-1, S-2, S-3).

The desktop user is in eira-clients and can reach every daemon socket, so the
socket is not the boundary: each method's access class is. These tests hold
the production daemons to that, and close S-1 (any client could write to
stated) and S-2 (stated.sync_push committed part of a mixed batch).
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.state import State
from app.daemons.base import JsonRpcServer
from app.ipc import access

ROOT = Path(__file__).resolve().parents[1]

# Client-callable writes with no caller or proof check that are known and
# planned. The list may only shrink: a method that is fixed must be removed
# here, and a new open write fails the test.
KNOWN_OPEN_WRITES = {
    ("identityd", "identity.session"): "F1.5",
    ("identityd", "identity.verify_production_certificate"): "F0b.4",
    ("intentd", "dashboard.get"): "F1.5",
    ("intentd", "presentation.mode_get"): "F1.5",
    ("intentd", "presentation.mode_set"): "F1.5",
    ("intentd", "intent.parse"): "F1.2",
    ("intentd", "intent.plan"): "F1.2",
}


@pytest.fixture(scope="module")
def catalogue() -> dict:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "ipc_catalog.py"), "--json"],
        capture_output=True, text=True, timeout=600, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout)


def test_every_production_daemon_is_in_the_catalogue(catalogue):
    policy = json.loads((ROOT / "packaging" / "daemon-policy.json").read_text())
    assert set(policy["production_daemons"]) | {"modeld"} == set(catalogue)


def test_every_production_method_has_an_access_class(catalogue):
    missing = [(d, m) for d, methods in catalogue.items() for m, i in methods.items() if not i["access"]]
    assert missing == []


def test_caller_methods_receive_the_kernel_caller(catalogue):
    blind = [(d, m) for d, methods in catalogue.items() for m, i in methods.items()
             if i["access"] == "caller" and not i["wants_peer"]]
    assert blind == []


def test_open_writes_are_exactly_the_known_planned_gaps(catalogue):
    found = {(d, m): i["note"] for d, methods in catalogue.items() for m, i in methods.items()
             if i["access"] == "open_write"}
    assert found == KNOWN_OPEN_WRITES


def test_stated_writes_are_daemon_only(catalogue):
    stated = catalogue["stated"]
    for method in ("state.append", "state.sync_push", "audit.append"):
        assert stated[method]["access"] == "daemon_write", method


def test_catalogue_document_is_current():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "ipc_catalog.py"), "--check"],
        capture_output=True, text=True, timeout=600, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr


# --- the server enforces the class ------------------------------------------------------


def test_a_method_without_a_class_cannot_be_registered():
    with pytest.raises(ValueError, match="no access class"):
        JsonRpcServer("test", "test").register("x", lambda _: {})


def test_a_caller_method_must_take_the_caller():
    with pytest.raises(TypeError):
        access.caller(lambda _: {})


def test_an_open_write_must_name_its_plan():
    with pytest.raises(ValueError):
        access.open_write(lambda _: {}, "")


def _call(server: JsonRpcServer, peer, method: str = "w") -> dict:
    line = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": {}})
    return json.loads(server.handle_line(line, peer))


def _write_server() -> tuple[JsonRpcServer, list]:
    calls: list = []
    server = JsonRpcServer("test", "test")
    server.register("w", access.daemon_write(lambda params: calls.append(params) or {"ok": True}))
    return server, calls


def test_daemon_write_from_another_user_is_refused_before_the_handler():
    server, calls = _write_server()
    reply = _call(server, SimpleNamespace(uid=os.getuid() + 1, gid=0, pid=1, groups=frozenset()))
    assert reply["error"]["code"] == access.ACCESS_DENIED
    assert reply["error"]["message"] == "E_ACCESS_DAEMON_ONLY"
    assert reply["error"]["data"]["user_message"]
    assert calls == []


def test_daemon_write_without_a_kernel_caller_is_refused():
    server, calls = _write_server()
    assert _call(server, None)["error"]["code"] == access.ACCESS_DENIED
    assert calls == []


def test_daemon_write_from_the_service_user_runs():
    server, calls = _write_server()
    reply = _call(server, SimpleNamespace(uid=os.getuid(), gid=0, pid=1, groups=frozenset()))
    assert reply["result"] == {"ok": True}
    assert len(calls) == 1


def test_root_is_not_a_daemon_writer_unless_it_is_the_service_user(monkeypatch):
    monkeypatch.setattr(access, "service_uid", lambda: 999)
    server, calls = _write_server()
    assert _call(server, SimpleNamespace(uid=0, gid=0, pid=1, groups=frozenset()))["error"]
    assert calls == []


# --- stated: S-1 and S-2 ----------------------------------------------------------------


@pytest.fixture()
def stated(tmp_path, monkeypatch):
    monkeypatch.setenv("EIRA_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("EIRA_STATE_BACKEND", "python")
    import app.daemons.stated as module

    module = importlib.reload(module)
    server = JsonRpcServer("stated", "stated")
    module.register_state_handlers(server)
    return SimpleNamespace(module=module, server=server)


def _valid_state() -> dict:
    """A state whose hash matches its content (State computes it when empty)."""
    return State(id=uuid4(), version=1, timestamp_ns=1, type="Note", payload={"n": 1}).model_dump(mode="json")


@pytest.mark.parametrize("method", ["state.append", "state.sync_push", "audit.append"])
def test_the_desktop_user_cannot_write_to_stated(stated, method):
    user = SimpleNamespace(uid=os.getuid() + 1, gid=0, pid=1, groups=frozenset())
    line = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": {"type": "Note", "payload": {}, "event_type": "x", "states": []}})
    reply = json.loads(stated.server.handle_line(line, user))
    assert reply["error"]["message"] == "E_ACCESS_DAEMON_ONLY"


def test_a_mixed_sync_batch_writes_nothing(stated):
    good = _valid_state()
    bad = dict(_valid_state(), hash="0" * 64)
    result = stated.module.state_sync_push({"states": [good, bad]})
    assert result["status"] == "rejected"
    assert result["accepted"] == 0
    assert stated.module._store.get_by_id(State(**good).id) is None


def test_a_sync_conflicting_with_a_stored_state_is_rejected(stated):
    first = _valid_state()
    assert stated.module.state_sync_push({"states": [first]})["accepted"] == 1
    other = dict(_valid_state(), id=first["id"])
    result = stated.module.state_sync_push({"states": [other]})
    assert result["status"] == "rejected"


def test_a_valid_sync_batch_is_written_and_repeats_are_skipped(stated):
    batch = [_valid_state(), _valid_state()]
    assert stated.module.state_sync_push({"states": batch}) == {
        "status": "synced", "accepted": 2, "skipped": 0, "invalid": 0}
    assert stated.module.state_sync_push({"states": batch})["skipped"] == 2
