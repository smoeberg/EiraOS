"""The package installs exactly the production import closure of app/.

debian/rules installs the files in packaging/app-modules.txt instead of
copying all of app/. These tests keep that list honest: it must equal the
closure scripts/app_modules.py computes, it must never contain the dev HTTP
bridge, its routers or prototype daemons, and an installed tree built from
it must import every production entry point on its own.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIST = ROOT / "packaging" / "app-modules.txt"


def _load_script():
    spec = importlib.util.spec_from_file_location("app_modules", ROOT / "scripts" / "app_modules.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _listed() -> list[str]:
    return [line for line in LIST.read_text().splitlines() if line and not line.startswith("#")]


def test_list_matches_the_import_closure():
    assert _listed() == _load_script().closure(), (
        "packaging/app-modules.txt is out of date: run scripts/app_modules.py --write"
    )


def test_list_has_no_dev_or_prototype_modules():
    policy = json.loads((ROOT / "packaging" / "daemon-policy.json").read_text())
    forbidden = {"app/http_bridge.py", "app/main.py"} | {
        f"app/daemons/{name}.py" for name in policy["prototype_daemons"]
    }
    listed = set(_listed())
    assert not listed & forbidden
    assert not [path for path in listed if path.startswith("app/routers/")]


def test_debian_rules_installs_the_list_not_all_of_app():
    rules = (ROOT / "packaging" / "debian" / "rules").read_text()
    assert "cp -a app" not in rules
    assert "packaging/app-modules.txt" in rules
    assert "diff -u - debian/app-modules.closure" in rules


def test_installed_tree_imports_every_production_entry_point(tmp_path):
    """Install the listed files as debian/rules does and import the entry
    points from that tree alone, outside the source checkout."""
    for relative in _listed():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    script = _load_script()
    policy = json.loads((ROOT / "packaging" / "daemon-policy.json").read_text())
    modules = list(script.COMMAND_MODULES) + [f"app.daemons.{d}" for d in policy["production_daemons"]]
    code = (
        "import importlib, sys\n"
        f"sys.path.insert(0, {str(tmp_path)!r})\n"
        f"for m in {modules!r}:\n"
        "    mod = importlib.import_module(m)\n"
        f"    assert mod.__file__.startswith({str(tmp_path)!r}), (m, mod.__file__)\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr[-2000:]
