"""A software TPM (swtpm) for tests of the device key (EIRA-CONTEXT §5.0).

``SoftTpm`` starts one swtpm instance with its own state; two instances are
two different TPMs, which is how the tests model a cloned disk on new
hardware (A-1). Needs ``swtpm`` and the OpenSSL ``tpm2`` provider
(``tpm2-openssl``); without them the tests skip, and with
EIRA_TEST_REQUIRE_TPM=1 (CI) they fail instead.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OPENSSL_CNF = ROOT / "packaging" / "rights" / "openssl-tpm2.cnf"


def _modules_dir() -> str | None:
    try:
        out = subprocess.run(["openssl", "version", "-m"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    directory = out.split('"')[1] if '"' in out else None
    return directory if directory and Path(directory, "tpm2.so").exists() else None


def require_tpm_tools() -> None:
    missing = [] if shutil.which("swtpm") else ["swtpm"]
    if _modules_dir() is None:
        missing.append("the OpenSSL tpm2 provider (tpm2-openssl)")
    if missing:
        reason = f"no software TPM: install {' and '.join(missing)}"
        if os.environ.get("EIRA_TEST_REQUIRE_TPM") == "1":
            pytest.fail(reason)
        pytest.skip(reason)


def _free_port_pair() -> int:
    """A free port whose successor is free too: the swtpm TCTI expects the
    control channel on port + 1."""
    for _ in range(50):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        try:
            with socket.socket() as a, socket.socket() as b:
                a.bind(("127.0.0.1", port))
                b.bind(("127.0.0.1", port + 1))
            return port
        except OSError:
            continue
    raise RuntimeError("no free port pair for swtpm")


class SoftTpm:
    def __init__(self) -> None:
        self.state = tempfile.mkdtemp(prefix="eira-swtpm-")
        self.port = _free_port_pair()
        ctrl = self.port + 1
        self.proc = subprocess.Popen(
            ["swtpm", "socket", "--tpm2", "--tpmstate", f"dir={self.state}",
             "--server", f"type=tcp,port={self.port},bindaddr=127.0.0.1",
             "--ctrl", f"type=tcp,port={ctrl},bindaddr=127.0.0.1",
             "--flags", "not-need-init,startup-clear"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.05)
        self.stop()
        raise RuntimeError("swtpm did not start")

    @property
    def tcti(self) -> str:
        return f"swtpm:host=127.0.0.1,port={self.port}"

    def env(self) -> dict[str, str]:
        """Environment for a process that uses this TPM through OpenSSL."""
        env = dict(os.environ, TPM2OPENSSL_TCTI=self.tcti, OPENSSL_CONF=str(OPENSSL_CNF))
        env["OPENSSL_MODULES"] = _modules_dir() or ""
        return env

    def run_python(self, code: str, *args: str) -> subprocess.CompletedProcess:
        """Run Python with OpenSSL's tpm2 provider loaded (as eira-rights-sync does)."""
        return subprocess.run([sys.executable, "-c", code, *args], env=self.env(), cwd=ROOT,
                              capture_output=True, text=True, timeout=60)

    def stop(self) -> None:
        self.proc.terminate()
        self.proc.wait(timeout=10)
        shutil.rmtree(self.state, ignore_errors=True)


@pytest.fixture
def tpm(monkeypatch):
    """This device's TPM: OpenSSL in this process (via the openssl CLI) uses it."""
    require_tpm_tools()
    device = SoftTpm()
    monkeypatch.setenv("TPM2OPENSSL_TCTI", device.tcti)
    yield device
    device.stop()


@pytest.fixture
def other_tpm():
    """Another machine's TPM: the cloned disk boots here (A-1)."""
    require_tpm_tools()
    device = SoftTpm()
    yield device
    device.stop()
