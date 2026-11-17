"""Operating limits and a watchdog for the daemons (UDVIKLINGSPLAN F1c.13,
vurderingen G-39).

Every long-running unit has MemoryMax, TasksMax and a start limit. The gate
(intentd) is Type=notify with WatchdogSec: it tells systemd when it serves,
and it is pinged for only while it answers its own health call, so a gate
that hangs is killed and restarted. A daemon at its thread limit refuses the
connection and keeps accepting.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from app.daemons import service_notify
from app.daemons.base import JsonRpcServer
from app.daemons.runner import start_daemons, stop_daemons
from app.daemons.service_notify import ServiceNotifier, notify, watchdog_interval
from app.ipc.access import read
from app.ipc.client import IpcClient

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "packaging" / "daemon-policy.json").read_text(encoding="utf-8"))
DAEMON_UNITS = {d: ROOT / "systemd" / f"eira-{d}.service" for d in POLICY["production_daemons"]}
UNITS = DAEMON_UNITS | {"modeld": ROOT / "packaging" / "model" / "eira-modeld.service"}
# Units with a watchdog: the gate first (the plan). Each needs the notify
# rules in its AppArmor profile, or systemd kills a healthy daemon.
WATCHED = {"intentd"}


def _sections(path: Path) -> dict[str, dict[str, list[str]]]:
    """A unit file as section -> key -> values (keys repeat: Environment=)."""
    sections: dict[str, dict[str, list[str]]] = {}
    current: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], {})
            continue
        key, _, value = line.partition("=")
        current.setdefault(key, []).append(value)
    return sections


def _bytes(value: str) -> int:
    units = {"K": 2**10, "M": 2**20, "G": 2**30}
    return int(value[:-1]) * units[value[-1]] if value[-1] in units else int(value)


# --- the units ------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(UNITS))
def test_every_long_running_unit_has_memory_and_task_limits(name):
    service = _sections(UNITS[name])["Service"]
    (memory,) = service["MemoryMax"]
    (tasks,) = service["TasksMax"]
    # A limit, and far above what the daemons use idle (20 to 46 MB, 2 to 5
    # threads): the VM check unit-limits-headroom measures it after a full run.
    assert 256 * 2**20 <= _bytes(memory) <= 2**30
    assert 32 <= int(tasks) <= 512


@pytest.mark.parametrize("name", sorted(UNITS))
def test_every_long_running_unit_has_a_start_limit_in_the_unit_section(name):
    sections = _sections(UNITS[name])
    unit, service = sections["Unit"], sections["Service"]
    # [Unit], not [Service]: systemd ignores them in [Service] with a warning.
    assert "StartLimitIntervalSec" not in service and "StartLimitBurst" not in service
    (interval,) = unit["StartLimitIntervalSec"]
    (burst,) = unit["StartLimitBurst"]
    (restart_sec,) = service["RestartSec"]
    assert restart_sec == "2s" and interval.endswith("s")
    # A crash loop must be able to reach the limit: more starts than the
    # burst fit in the interval at RestartSec. (systemd's default, 5 in 10 s,
    # is never reached at 2 s, so a crash loop ran for ever.)
    assert int(interval[:-1]) / 2 > int(burst) >= 5


@pytest.mark.parametrize("name", sorted(WATCHED))
def test_a_watched_unit_notifies_and_is_killed_without_a_core_dump(name):
    service = _sections(UNITS[name])["Service"]
    assert service["Type"] == ["notify"]
    assert service["NotifyAccess"] == ["main"]
    assert service["WatchdogSec"] == ["30s"]
    assert service["Restart"] == ["always"]  # a watchdog kill is restarted
    # SIGKILL, not the default SIGABRT: no core dump of a process that holds
    # sessions, and it works on a process that is stopped.
    assert service["WatchdogSignal"] == ["SIGKILL"]
    profile = (ROOT / "packaging" / "apparmor" / f"usr.bin.eira-{name}").read_text(encoding="utf-8")
    assert "  /run/systemd/notify rw,\n" in profile
    assert "  network unix dgram,\n" in profile


@pytest.mark.parametrize("name", sorted(set(UNITS) - WATCHED))
def test_an_unwatched_unit_has_no_watchdog_it_could_not_feed(name):
    service = _sections(UNITS[name])["Service"]
    assert "WatchdogSec" not in service
    assert service["Type"] == ["simple"]


def test_the_wrapper_execs_so_the_daemon_is_the_main_pid():
    # NotifyAccess=main: the notification must come from the unit's main PID.
    wrapper = (ROOT / "packaging" / "bin" / "eira-daemon").read_text(encoding="utf-8")
    assert "\nexec /usr/bin/python3 -m app.daemons.runner" in wrapper


# --- sd_notify --------------------------------------------------------------------------


@pytest.fixture()
def systemd(tmp_path, monkeypatch):
    """A stand-in for systemd's notification socket; returns what arrived."""
    directory = Path(tempfile.mkdtemp(prefix="eira-n-"))
    address = str(directory / "notify")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind(address)
    sock.settimeout(0.2)
    monkeypatch.setenv("NOTIFY_SOCKET", address)
    monkeypatch.delenv("WATCHDOG_USEC", raising=False)
    monkeypatch.delenv("WATCHDOG_PID", raising=False)

    def received() -> list[str]:
        messages = []
        while True:
            try:
                messages.append(sock.recv(4096).decode("ascii"))
            except TimeoutError:
                return messages

    yield received
    sock.close()
    os.unlink(address)
    os.rmdir(directory)


def test_without_systemd_nothing_is_sent_and_nothing_fails(monkeypatch):
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    monkeypatch.delenv("WATCHDOG_USEC", raising=False)
    assert notify("READY=1") is False
    notifier = ServiceNotifier(["stated"], probe=lambda _: True)
    assert notifier.interval is None and notifier.tick() is False
    notifier.ready()
    notifier.stopping()


def test_a_socket_that_is_gone_is_a_warning_not_a_crash(monkeypatch, tmp_path):
    monkeypatch.setenv("NOTIFY_SOCKET", str(tmp_path / "no-such-socket"))
    assert notify("READY=1") is False


def test_ready_and_stopping_reach_systemd(systemd):
    notifier = ServiceNotifier(["stated"], probe=lambda _: True)
    notifier.ready()
    notifier.stopping()
    assert systemd() == ["READY=1", "STOPPING=1"]


def test_the_ping_interval_is_a_third_of_the_period(monkeypatch):
    monkeypatch.setenv("WATCHDOG_USEC", "30000000")
    monkeypatch.delenv("WATCHDOG_PID", raising=False)
    assert watchdog_interval() == 10.0
    monkeypatch.setenv("WATCHDOG_PID", str(os.getpid()))
    assert watchdog_interval() == 10.0
    monkeypatch.setenv("WATCHDOG_PID", str(os.getpid() + 1))  # meant for another process
    assert watchdog_interval() is None
    for bad in ("", "0", "soon", "-5"):
        monkeypatch.setenv("WATCHDOG_USEC", bad)
        monkeypatch.delenv("WATCHDOG_PID", raising=False)
        assert watchdog_interval() is None, bad


def test_a_ping_is_sent_only_while_every_daemon_answers(systemd, monkeypatch):
    monkeypatch.setenv("WATCHDOG_USEC", "3000000")
    state = {"stated": True, "intentd": True}
    notifier = ServiceNotifier(state, probe=lambda daemon: state[daemon])
    assert notifier.tick() is True
    state["intentd"] = False
    assert notifier.tick() is False
    state["intentd"] = True
    assert notifier.tick() is True
    assert systemd() == ["WATCHDOG=1", "WATCHDOG=1"]


def test_no_daemons_is_not_healthy(systemd, monkeypatch):
    monkeypatch.setenv("WATCHDOG_USEC", "3000000")
    assert ServiceNotifier([], probe=lambda _: True).tick() is False
    assert systemd() == []


# --- the probe goes through the real socket ------------------------------------------------


@pytest.fixture()
def run_dir(monkeypatch):
    stop_daemons()
    directory = Path(tempfile.mkdtemp(prefix="eira-w-"))
    monkeypatch.setenv("EIRA_RUN_DIR", str(directory))
    yield directory
    stop_daemons()
    for leftover in directory.iterdir():
        leftover.unlink()
    directory.rmdir()


def test_a_serving_daemon_answers_and_a_stopped_one_does_not(run_dir):
    start_daemons("stated", run_dir)
    assert service_notify.answers("stated", timeout=2)
    stop_daemons()
    assert not service_notify.answers("stated", timeout=1)


def test_a_daemon_whose_handling_is_stuck_does_not_answer(run_dir):
    release = threading.Event()
    server = JsonRpcServer("eira-stated", "stated")
    server.register("health", read(lambda _: release.wait(10) and {"ok": True}))
    server.start()
    try:
        assert not service_notify.answers("stated", timeout=0.3)
        release.set()
        assert service_notify.answers("stated", timeout=2)
    finally:
        release.set()
        server.stop()


def test_a_wrong_answer_is_not_healthy(run_dir):
    server = JsonRpcServer("eira-stated", "stated")
    server.register("health", read(lambda _: {"ok": False}))
    server.start()
    try:
        assert not service_notify.answers("stated", timeout=2)
    finally:
        server.stop()


# --- at the thread limit the daemon refuses, it does not stop serving ---------------------------


def test_a_failed_thread_start_refuses_one_connection_and_keeps_accepting(run_dir, monkeypatch):
    server = JsonRpcServer("eira-stated", "stated")
    server.register("health", read(lambda _: {"ok": True}))
    server.start()
    real_start = threading.Thread.start
    refused = []

    def start(thread):
        # What TasksMax does: pthread_create fails, Python raises RuntimeError.
        if not refused and thread._target == server._serve_client:  # noqa: SLF001
            refused.append(thread)
            raise RuntimeError("can't start new thread")
        return real_start(thread)

    monkeypatch.setattr(threading.Thread, "start", start)
    try:
        with pytest.raises(Exception):  # noqa: B017, PT011 - closed without an answer
            IpcClient("stated", timeout=2).call("health")
        assert refused
        assert server._connections == set()  # noqa: SLF001 - the refused one is not kept
        assert IpcClient("stated", timeout=2).call("health") == {"ok": True}
        assert service_notify.answers("stated", timeout=2)
    finally:
        server.stop()


# --- the runner under a stand-in systemd -------------------------------------------------------


def test_the_runner_says_ready_pings_while_it_serves_and_stops_when_it_hangs(systemd, run_dir):
    env = os.environ | {"EIRA_RUN_DIR": str(run_dir), "WATCHDOG_USEC": "900000",
                        "EIRA_STATE_DB": str(run_dir / "state.db")}
    env.pop("WATCHDOG_PID", None)
    process = subprocess.Popen(
        [sys.executable, "-m", "app.daemons.runner", "--daemon", "stated", "--socket-dir", str(run_dir)],
        env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    try:
        seen: list[str] = []
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and seen.count("WATCHDOG=1") < 2:
            seen += systemd()
        assert seen[0] == "READY=1", (seen, process.poll())
        assert seen.count("WATCHDOG=1") >= 2
        # READY came after the socket served, not before.
        assert (run_dir / "stated.sock").exists()

        # A hung process (stopped) sends nothing more: systemd's timer runs out.
        process.send_signal(signal.SIGSTOP)
        systemd()
        time.sleep(1.2)
        assert systemd() == []
        process.send_signal(signal.SIGCONT)

        process.send_signal(signal.SIGTERM)
        process.wait(timeout=10)
        assert "STOPPING=1" in systemd()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
