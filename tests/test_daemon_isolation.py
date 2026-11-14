"""The daemons are isolated from each other (UDVIKLINGSPLAN F1c.3; vurderingen
G-3, G-35).

All seven daemons and the rights sync run as the same user (eira), so the UID
alone cannot say which daemon is calling. A ``daemon_write`` method names the
daemons that may call it, and the server asks the kernel which daemon the
caller is: its AppArmor label (SO_PEERSEC), else its systemd unit's cgroup.
The AppArmor profiles let each daemon create only its own socket and connect
only to the daemons it calls; no daemon shares a log directory.
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.daemons.base import JsonRpcServer
from app.ipc import access

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "packaging" / "daemon-policy.json").read_text(encoding="utf-8"))
APPARMOR = ROOT / "packaging" / "apparmor"
ME = os.getuid()


def _peer(*, uid: int = ME, label: str | None = None, pid: int = 1) -> SimpleNamespace:
    return SimpleNamespace(uid=uid, gid=0, pid=pid, groups=frozenset(), label=label)


def _label(daemon: str, mode: str = "enforce") -> str:
    return f"/usr/bin/eira-{daemon} ({mode})"


@pytest.fixture()
def strict(monkeypatch):
    monkeypatch.setenv("EIRA_STRICT_DAEMON_IDENTITY", "1")


@pytest.fixture()
def cgroups(tmp_path, monkeypatch):
    """A fake /proc: pid -> the contents of its cgroup file."""
    proc = tmp_path / "proc"

    def write(pid: int, text: str) -> int:
        (proc / str(pid)).mkdir(parents=True, exist_ok=True)
        (proc / str(pid) / "cgroup").write_text(text, encoding="ascii")
        return pid

    real = access.daemon_from_cgroup
    monkeypatch.setattr(access, "daemon_from_cgroup", lambda pid, proc_=proc: real(pid, proc_))
    return write


# --- which daemon the kernel says the caller is ------------------------------------


@pytest.mark.parametrize("daemon", sorted(access.DAEMONS))
def test_an_enforced_daemon_profile_names_the_daemon(daemon):
    assert access.daemon_from_label(_label(daemon)) == daemon


@pytest.mark.parametrize("label", [
    None, "", "unconfined", _label("fleetd", "complain"), "/usr/bin/eira-modeld (enforce)",
    "/usr/bin/eira-rights-apply (enforce)", "/usr/lib/eira-os/eira-consent-agent (enforce)",
    "/usr/local/bin/eira-stated (enforce)", "/usr/bin/eira-stated",
])
def test_anything_else_is_no_daemon(label):
    assert access.daemon_from_label(label) is None


def test_the_cgroup_names_the_unit(cgroups):
    pid = cgroups(4242, "0::/system.slice/eira-fleetd.service\n")
    assert access.peer_daemon(_peer(pid=pid)) == "fleetd"


@pytest.mark.parametrize("text", [
    "0::/system.slice/eira-rights-sync.service\n",
    "0::/system.slice/eira-ci-report.service\n",
    "0::/user.slice/user-1000.slice/session-2.scope\n",
    "0::/system.slice/eira-fleetd.service/extra\n",
    "",
])
def test_other_units_are_no_daemon(cgroups, text):
    assert access.peer_daemon(_peer(pid=cgroups(4243, text))) is None


def test_a_confined_caller_is_decided_by_its_label_not_its_cgroup(cgroups):
    # rights-sync runs under its own profile; even in a daemon's unit
    # (intentd's ExecStartPre) only the label counts.
    pid = cgroups(4244, "0::/system.slice/eira-stated.service\n")
    assert access.peer_daemon(_peer(pid=pid, label="/usr/bin/eira-rights-apply (enforce)")) is None
    assert access.peer_daemon(_peer(pid=pid, label=_label("fleetd"))) == "fleetd"


def test_an_unconfined_caller_is_decided_by_its_cgroup(cgroups):
    pid = cgroups(4245, "0::/system.slice/eira-delegationd.service\n")
    assert access.peer_daemon(_peer(pid=pid, label="unconfined")) == "delegationd"


def test_a_missing_process_is_no_daemon(cgroups):
    assert access.peer_daemon(_peer(pid=999_999)) is None
    assert access.peer_daemon(_peer(pid=0)) is None


# --- daemon_write: named daemons, service UID ------------------------------------------


def test_a_named_daemon_with_the_service_uid_may_write(strict):
    assert access.daemon_write_allowed(_peer(label=_label("fleetd")), {"fleetd"})


def test_another_daemon_may_not(strict):
    assert not access.daemon_write_allowed(_peer(label=_label("graphd")), {"fleetd"})


def test_no_daemon_may_write_a_method_without_callers(strict):
    for daemon in access.DAEMONS:
        assert not access.daemon_write_allowed(_peer(label=_label(daemon)), ())


def test_the_desktop_user_under_a_daemon_profile_may_not(strict):
    # An unconfined process can change to any loaded profile; it cannot take
    # the service UID.
    assert not access.daemon_write_allowed(_peer(uid=ME + 1, label=_label("fleetd")), {"fleetd"})


def test_the_service_uid_alone_is_not_a_daemon_on_an_installed_system(strict, cgroups):
    pid = cgroups(4246, "0::/system.slice/eira-rights-sync.service\n")
    assert not access.daemon_write_allowed(_peer(pid=pid, label="unconfined"), {"fleetd"})
    assert not access.daemon_write_allowed(_peer(pid=pid), {"fleetd"})


def test_a_daemon_profile_in_complain_mode_is_not_the_daemon(strict):
    assert not access.daemon_write_allowed(_peer(label=_label("fleetd", "complain")), {"fleetd"})


def test_a_development_run_accepts_the_service_uid(monkeypatch, cgroups):
    monkeypatch.setenv("EIRA_STRICT_DAEMON_IDENTITY", "0")
    pid = cgroups(4247, "0::/user.slice/session-1.scope\n")
    assert access.daemon_write_allowed(_peer(pid=pid), {"fleetd"})
    # A named daemon is still held to the list, even in development.
    assert not access.daemon_write_allowed(_peer(label=_label("graphd")), {"fleetd"})
    assert not access.daemon_write_allowed(_peer(uid=ME + 1, pid=pid), {"fleetd"})


def test_an_installed_system_is_strict(monkeypatch):
    monkeypatch.delenv("EIRA_STRICT_DAEMON_IDENTITY", raising=False)
    monkeypatch.setenv("EIRA_RUN_DIR", "/run/eira")
    assert access.strict_daemon_identity()
    monkeypatch.setenv("EIRA_RUN_DIR", "/tmp/eira-dev")
    assert not access.strict_daemon_identity()


def test_callers_must_be_known_daemons():
    with pytest.raises(ValueError):
        access.daemon_write(lambda _: {}, callers=("fleet",))
    with pytest.raises(TypeError):
        access.daemon_write(lambda _: {}, callers="fleetd")
    with pytest.raises(TypeError):
        access.daemon_write(lambda _: {})  # type: ignore[call-arg]


# --- the server, end to end: stated -------------------------------------------------


@pytest.fixture()
def stated(tmp_path, monkeypatch, strict):
    import importlib

    monkeypatch.setenv("EIRA_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("EIRA_STATE_BACKEND", "python")
    import app.daemons.stated as module

    module = importlib.reload(module)
    server = JsonRpcServer("stated", "stated")
    module.register_state_handlers(server)
    return server


def _call(server, method: str, params: dict, peer) -> dict:
    line = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    return json.loads(server.handle_line(line, peer))


AUDIT = {"event_type": "test", "actor_id": "x", "details": {}}


@pytest.mark.parametrize("daemon", ["identityd", "delegationd"])
def test_the_auditing_daemons_may_append_to_the_audit_trail(stated, daemon):
    reply = _call(stated, "audit.append", AUDIT, _peer(label=_label(daemon)))
    assert reply["result"]["status"] == "appended", reply


@pytest.mark.parametrize("daemon", ["fleetd", "graphd", "veritasd", "intentd", "stated"])
def test_other_daemons_may_not_append_to_the_audit_trail(stated, daemon):
    reply = _call(stated, "audit.append", AUDIT, _peer(label=_label(daemon)))
    assert reply["error"]["message"] == "E_ACCESS_DAEMON_ONLY", reply


@pytest.mark.parametrize("daemon", sorted(access.DAEMONS - {"fleetd"}))
def test_only_fleetd_may_append_states(stated, daemon):
    reply = _call(stated, "state.append", {"type": "Forged", "payload": {}}, _peer(label=_label(daemon)))
    assert reply["error"]["message"] == "E_ACCESS_DAEMON_ONLY", reply


def test_no_daemon_may_use_the_unused_batch_path(stated):
    for daemon in access.DAEMONS:
        reply = _call(stated, "state.sync_push", {"states": []}, _peer(label=_label(daemon)))
        assert reply["error"]["message"] == "E_ACCESS_DAEMON_ONLY", (daemon, reply)


def test_the_rights_sync_may_not_write_state(stated):
    peer = _peer(label="/usr/bin/eira-rights-apply (enforce)")
    for method, params in (("audit.append", AUDIT), ("state.append", {"type": "F", "payload": {}})):
        assert _call(stated, method, params, peer)["error"]["message"] == "E_ACCESS_DAEMON_ONLY"


# --- the code's calls match the policy and the profiles -----------------------------


# Every IpcClient("<daemon>") in app/, with the daemon process it runs in. A new
# call fails here until it is listed, and the policy then decides whether that
# daemon may connect (packaging/daemon-policy.json "ipc_connects").
CALL_SITES = {
    "app/auth/delegation.py": ("delegationd", "stated"),
    "app/core/remote_store.py": ("fleetd", "stated"),
    "app/daemons/graphd.py": ("graphd", "stated"),
    "app/daemons/identityd.py": ("identityd", "stated"),
    "app/veritas/layer3_graph.py": ("veritasd", "graphd"),
    # Not daemons: the dev HTTP bridge, the CLI and the model (own profile).
    "app/routers/common.py": (None, None),
    "app/cli/delegation.py": (None, None),
    "app/model/daemon.py": (None, None),
}


def _ipc_client_targets() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in (ROOT / "app").rglob("*.py"):
        if path.name == "client.py" and path.parent.name == "ipc":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "IpcClient"):
                rel = str(path.relative_to(ROOT))
                arg = node.args[0] if node.args else None
                target = arg.value if isinstance(arg, ast.Constant) else "?"
                found.setdefault(rel, set()).add(target)
    return found


def test_every_ipc_call_site_is_known():
    assert set(_ipc_client_targets()) == set(CALL_SITES)


def test_every_daemon_call_is_allowed_by_the_policy():
    from app.ipc.paths import canonical_daemon

    connects = POLICY["ipc_connects"]
    for path, targets in _ipc_client_targets().items():
        caller, expected = CALL_SITES[path]
        if caller is None:
            continue
        assert {canonical_daemon(t) for t in targets} == {expected}, path
        assert expected in connects[caller], (caller, expected)


def test_the_policy_lists_exactly_the_calls():
    calls: dict[str, set[str]] = {d: set() for d in POLICY["production_daemons"]}
    for caller, target in CALL_SITES.values():
        if caller is not None:
            calls[caller].add(target)
    assert {d: set(t) for d, t in POLICY["ipc_connects"].items()} == calls


SOCKET_RULE = re.compile(r"^\s*(/run/eira/\S*\.sock)\s+(\w+),", re.M)


@pytest.mark.parametrize("daemon", POLICY["production_daemons"])
def test_each_profile_owns_its_socket_and_reaches_only_its_callees(daemon):
    text = (APPARMOR / f"usr.bin.eira-{daemon}").read_text(encoding="utf-8")
    rules = dict(SOCKET_RULE.findall(text))
    expected = {f"/run/eira/{daemon}.sock": "rwk"}
    expected |= {f"/run/eira/{t}.sock": "rw" for t in POLICY["ipc_connects"][daemon]}
    assert rules == expected
    assert "/var/log/eira" not in text


@pytest.mark.parametrize("daemon", POLICY["production_daemons"])
def test_no_daemon_unit_shares_a_log_directory(daemon):
    unit = (ROOT / "systemd" / f"eira-{daemon}.service").read_text(encoding="utf-8")
    assert "LogsDirectory" not in unit
    assert "/var/log/eira" not in unit


def test_the_servers_that_take_daemon_writes_can_read_the_callers_cgroup():
    for daemon in ("stated", "identityd"):
        text = (APPARMOR / f"usr.bin.eira-{daemon}").read_text(encoding="utf-8")
        assert "@{PROC}/[0-9]*/cgroup r," in text, daemon
