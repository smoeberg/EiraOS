"""Installed daemons may only import what the Debian package depends on.

The dev environment has everything in requirements.txt; an installed system
has only debian/control. identityd once died at start on Ubuntu because
oidc imported app.config, which needs pydantic-settings (found only in the
VM). This test registers every installed Python daemon in a fresh process
with the dev-only packages made unimportable."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEV_ONLY = ["fastapi", "uvicorn", "pydantic_settings", "slowapi", "starlette"]
INSTALLED = sorted(
    p.stem.removeprefix("eira-") for p in (ROOT / "systemd").glob("eira-*.service")
    if p.stem.removeprefix("eira-") != "stated"  # Rust
)

PROBE = """
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {blocked!r}:
            raise ModuleNotFoundError(f"{{name}} is not in debian/control")
        return None
sys.meta_path.insert(0, Block())
from app.daemons.runner import REGISTRARS
class Server:
    def register(self, name, handler): pass
    def add_cleanup(self, callback): pass
REGISTRARS[{daemon!r}](Server())
"""


def test_every_installed_python_daemon_is_covered():
    assert {"identityd", "intentd", "graphd", "veritasd", "fleetd"} <= set(INSTALLED)


@pytest.mark.parametrize("daemon", INSTALLED)
def test_daemon_registers_without_dev_only_packages(daemon, tmp_path):
    env = {
        "PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT), "HOME": str(tmp_path),
        "EIRA_DB_PATH": str(tmp_path / "app.db"), "EIRA_APP_DB": str(tmp_path / "app.db"),
        "EIRA_RUN_DIR": str(tmp_path / "run"), "EIRA_RIGHTS_DIR": str(tmp_path / "rights"),
        "EIRA_DATA_DIR": str(tmp_path / "data"),
    }
    result = subprocess.run(
        [sys.executable, "-c", PROBE.format(blocked=set(DEV_ONLY), daemon=daemon)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr[-2000:]
