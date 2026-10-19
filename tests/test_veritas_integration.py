from __future__ import annotations

import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from app.daemons.base import JsonRpcServer
from app.daemons.veritasd import (\n    VERITAS_WEIGHTS,\n    VeritasDaemon,\n    register_veritas_handlers,\n)
from app.ipc.client import IpcClient
from app.ipc.socket_security import PeerCredentials, socket_access_allowed


PAYLOAD = {"type": "text", "text": "A sourced test claim", "url": "https://example.test"}


class FixedLayer:
    def __init__(self, score: float) -> None:
        self.score = score

    def evaluate(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"score": self.score, "flags": [], "details": {}}


class FixedCredentialLayer:
    def __init__(self, score: float) -> None:
        self.score = score

    def verify(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"score": self.score, "flags": [], "details": {}}


class BrokenLayer:
    def evaluate(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("sensitive implementation detail")


class ExplodingMapping(Mapping[str, Any]):
    def __getitem__(self, key: str) -> Any:
        raise KeyError(key)

    def __iter__(self):
        raise RuntimeError("private failure detail")

    def __len__(self) -> int:
        return 1


def fixed_daemon(scores: tuple[float, float, float, float]) -> VeritasDaemon:
    return VeritasDaemon(
        layer1=FixedLayer(scores[0]),
        layer2=FixedCredentialLayer(scores[1]),
        layer3=FixedLayer(scores[2]),
        c2pa=FixedLayer(scores[3]),
    )


@pytest.fixture
def veritas_process() -> Any:
    # Keep the AF_UNIX path comfortably below the platform's ~108-byte limit.
    socket_dir = Path(tempfile.mkdtemp(prefix="ev-"))
    socket_file = socket_dir / "veritasd.sock"
    env = os.environ.copy()
    env["EIRA_RUN_DIR"] = str(socket_dir)
    process = subprocess.Popen(
        [
            sys.executable, "-m", "app.daemons.runner",
            "--daemon", "veritasd", "--socket-dir", str(socket_dir),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        deadline = time.monotonic() + 10
        while not socket_file.exists() and process.poll() is None:
            if time.monotonic() >= deadline:
                pytest.fail("veritasd did not create its socket within 10 seconds")
            time.sleep(0.05)
        assert socket_file.exists(), "veritasd exited before creating its socket"
        yield process, socket_dir, socket_file
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=3)
        if socket_file.exists() and stat.S_ISSOCK(socket_file.stat().st_mode):
            socket_file.unlink()
        try:
            socket_dir.rmdir()
        except OSError:
            pass


def test_veritas_evaluate_over_real_runner_ipc(veritas_process: Any) -> None:
    _process, _socket_dir, socket_file = veritas_process
    result = IpcClient("veritasd", timeout=3).call("veritas.evaluate", PAYLOAD)

    assert set(result["layers"]) == {"layer1", "layer2", "layer3", "c2pa"}
    expected = sum(
        VERITAS_WEIGHTS[name] * result["layers"][name]["score"]
        for name in VERITAS_WEIGHTS
    )
    assert result["trust_score"] == round(expected * 100, 2)
    assert result["hud_certificate"]["certificate_type"] == "EIRA_VERITAS_HUD_V1"
    assert socket_file.exists()


def test_socket_mode_is_exactly_0660(veritas_process: Any) -> None:
    _process, _socket_dir, socket_file = veritas_process
    info = socket_file.stat()
    assert stat.S_ISSOCK(info.st_mode)
    assert stat.S_IMODE(info.st_mode) == 0o660


def test_peer_credentials_allow_and_deny() -> None:
    allowed = PeerCredentials(pid=123, uid=1001, gid=2001)
    denied = PeerCredentials(pid=124, uid=3001, gid=3002)
    assert socket_access_allowed(
        allowed, allowed_uids={1001}, allowed_gids={2001}
    )
    assert not socket_access_allowed(
        denied, allowed_uids={1001}, allowed_gids={2001}
    )


def test_sigterm_exits_cleanly_and_removes_socket(veritas_process: Any) -> None:
    process, _socket_dir, socket_file = veritas_process
    process.send_signal(signal.SIGTERM)
    process.communicate(timeout=10)
    assert process.returncode == 0
    assert not socket_file.exists()


def test_trust_aggregation_all_layers_one() -> None:
    result = fixed_daemon((1.0, 1.0, 1.0, 1.0)).evaluate(PAYLOAD)
    assert result["trust_score"] == 100.0
    assert result["confidence"] == 1.0
    assert all(result["layers"][name]["score"] == 1.0 for name in VERITAS_WEIGHTS)


def test_trust_aggregation_all_layers_zero() -> None:
    result = fixed_daemon((0.0, 0.0, 0.0, 0.0)).evaluate(PAYLOAD)
    assert result["trust_score"] == 0.0
    assert result["confidence"] == 0.0
    assert all(result["layers"][name]["score"] == 0.0 for name in VERITAS_WEIGHTS)


def test_trust_aggregation_asymmetrical_uses_all_four_weights() -> None:
    scores = (1.0, 0.4, 0.7, 0.2)
    result = fixed_daemon(scores).evaluate(PAYLOAD)
    expected = (
        0.30 * scores[0] + 0.35 * scores[1]
        + 0.20 * scores[2] + 0.15 * scores[3]
    )
    assert result["trust_score"] == round(expected * 100, 2)
    assert set(result["layers"]) == {"layer1", "layer2", "layer3", "c2pa"}
    assert len(result["rationale"]) == 4
    assert all(any(label in item for item in result["rationale"]) for label in (
        "Lag 1", "Lag 2", "Lag 3", "C2PA"
    ))


def test_layer_exception_fails_closed_and_keeps_evaluation_available(monkeypatch: pytest.MonkeyPatch) -> None:
    server = JsonRpcServer(name="test-veritas-fail-closed", daemon="veritasd")
    daemon = VeritasDaemon(layer1=BrokenLayer())
    register_veritas_handlers(server, daemon)
    with tempfile.TemporaryDirectory(prefix="evf-") as socket_dir:
        monkeypatch.setenv("EIRA_RUN_DIR", socket_dir)
        try:
            server.start()
            failed_layer = IpcClient("veritasd", timeout=3).call(
                "veritas.evaluate", PAYLOAD
            )
            assert failed_layer["layers"]["layer1"]["score"] == 0.0
            assert "layer_error:layer1" in failed_layer["layers"]["layer1"]["flags"]
            assert failed_layer["trust_score"] < 100.0
            # The next RPC must still be served by the same live daemon.
            assert IpcClient("veritasd", timeout=3).call("health", {}) == {
                "daemon": "eira-veritasd", "ok": True
            }
        finally:
            server.stop()


def test_total_evaluation_exception_returns_zero_without_traceback() -> None:
    result = VeritasDaemon().evaluate(ExplodingMapping())
    assert result["trust_score"] == 0.0
    assert result["rationale"] == ["intern fejl"]
    assert result["hud_certificate"]["error"] == "RuntimeError"
    assert "private failure detail" not in str(result)


def test_health_smoke_over_real_runner_ipc(veritas_process: Any) -> None:
    assert IpcClient("veritasd", timeout=3).call("health", {}) == {
        "daemon": "eira-veritasd",
        "ok": True,
    }
