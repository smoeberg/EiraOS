"""Every Rust build uses a committed lock file (UDVIKLINGSPLAN F0c.6,
vurderingen G-30): a changed dependency needs a changed Cargo.lock.

Both workspaces (the root, with the consent agent that is in the package, and
ui/src-tauri, which the root excludes) have their lock committed, and every
cargo build, test and clippy in CI, the package build and the release script
passes --locked.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ".github/workflows/ci.yml",
    ".github/workflows/packaging-acceptance.yml",
    "packaging/debian/rules",
    "scripts/release_rc1.sh",
]
CARGO = re.compile(r"\bcargo (build|test|clippy|run|check)\b[^\n]*")


@pytest.mark.parametrize("lock", ["Cargo.lock", "ui/src-tauri/Cargo.lock"])
def test_the_lock_file_is_committed(lock):
    assert (ROOT / lock).is_file(), f"{lock} is missing"
    inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT,
                            capture_output=True, text=True)
    if inside.returncode != 0:
        # Some CI jobs test an exported tree without .git; there the file
        # being in the tree is the evidence that it was committed.
        return
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", lock], cwd=ROOT,
                             capture_output=True, text=True)
    assert tracked.returncode == 0, f"{lock} is not committed"


@pytest.mark.parametrize("path", FILES)
def test_every_cargo_command_is_locked(path):
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
    code = [line for line in lines
            if not line.lstrip().startswith(("#", "- name:", "name:"))]
    commands = [m.group(0) for line in code for m in CARGO.finditer(line)]
    assert commands, "the check must find the cargo commands it guards"
    unlocked = [c for c in commands if "--locked" not in c]
    assert unlocked == []


def test_the_tauri_build_in_the_package_is_locked():
    rules = (ROOT / "packaging" / "debian" / "rules").read_text(encoding="utf-8")
    assert "npm run tauri -- build --no-bundle -- --locked" in rules


def test_ci_no_longer_says_the_tauri_lock_is_ignored():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Cargo.lock is gitignored" not in ci
