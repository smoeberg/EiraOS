"""The shared rights vectors are versioned (UDVIKLINGSPLAN F1.9, fundregister S-20).

eira-fleet-control pins a version of tests/vectors/ and runs the signing
vectors against its signer (scripts/rights_vectors_conformance.py). A pinned
version must mean the same files on both sides, so a changed vector without
a new version fails here.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "tests" / "vectors"
MANIFEST = json.loads((VECTORS / "MANIFEST.json").read_text(encoding="utf-8"))


def _gen_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("gen_rights_vectors", ROOT / "scripts" / "gen_rights_vectors.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_matches_the_files_and_its_version():
    gen = _gen_module()
    assert MANIFEST["files"] == gen._file_hashes()
    assert MANIFEST["set_hash"] == gen.set_hash(MANIFEST["files"])
    assert MANIFEST["history"][str(MANIFEST["version"])] == MANIFEST["set_hash"]
    assert MANIFEST["version"] == max(int(v) for v in MANIFEST["history"])


def test_generator_reproduces_the_committed_vectors(tmp_path):
    out = tmp_path / "vectors"
    out.mkdir()
    shutil.copy(VECTORS / "MANIFEST.json", out / "MANIFEST.json")
    env = {**os.environ, "EIRA_VECTORS_OUT": str(out)}
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_rights_vectors.py")],
                            env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
    for name in MANIFEST["files"]:
        assert (out / name).read_bytes() == (VECTORS / name).read_bytes(), name
    assert (out / "MANIFEST.json").read_bytes() == (VECTORS / "MANIFEST.json").read_bytes()


def test_a_changed_vector_needs_a_new_version(tmp_path):
    out = tmp_path / "vectors"
    out.mkdir()
    manifest = {**MANIFEST, "history": {str(MANIFEST["version"]): "sha256:" + "0" * 64}}
    (out / "MANIFEST.json").write_text(json.dumps(manifest))
    env = {**os.environ, "EIRA_VECTORS_OUT": str(out)}
    script = str(ROOT / "scripts" / "gen_rights_vectors.py")
    refused = subprocess.run([sys.executable, script], env=env, capture_output=True, text=True, timeout=120)
    assert refused.returncode != 0 and "--bump" in refused.stderr
    bumped = subprocess.run([sys.executable, script, "--bump"], env=env, capture_output=True, text=True, timeout=120)
    assert bumped.returncode == 0, bumped.stderr[-2000:]
    assert json.loads((out / "MANIFEST.json").read_text())["version"] == MANIFEST["version"] + 1


def test_signing_vector_is_what_the_endpoint_verifies():
    signed = json.loads((VECTORS / "rights-signing" / "sign-rights-set-managed.json").read_text(encoding="utf-8"))
    applied = json.loads((VECTORS / "rights-set" / "apply-valid-managed.json").read_text(encoding="utf-8"))
    assert signed["expect_raw"] == applied["raw"]
    assert applied["expect"] == {"ok": True}


def _conformance(signer: str, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "rights_vectors_conformance.py"), "--signer", signer, *extra],
        capture_output=True, text=True, timeout=300, cwd=ROOT,
    )


def test_reference_signer_conforms():
    result = _conformance(f"{sys.executable} scripts/rights_reference_signer.py",
                          "--expect-version", str(MANIFEST["version"]))
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PASS ") == len(list((VECTORS / "rights-signing").glob("*.json")))


def test_a_signer_that_escapes_unicode_or_drops_the_domain_fails(tmp_path):
    # Two realistic Fleet mistakes: json.dumps' default ensure_ascii, and
    # signing the JSON without the domain prefix.
    for name, patch in (
        ("ascii", ("ensure_ascii=False", "ensure_ascii=True")),
        ("no-domain", ("return bytes([len(DOMAIN)]) + DOMAIN + canonical(unsigned)", "return canonical(unsigned)")),
    ):
        tree = tmp_path / name
        shutil.copytree(ROOT / "app", tree / "app", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "scripts", tree / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        contract = tree / "app" / "rights" / "contract.py"
        text = contract.read_text(encoding="utf-8")
        assert patch[0] in text
        contract.write_text(text.replace(patch[0], patch[1]), encoding="utf-8")
        result = _conformance(f"{sys.executable} {tree / 'scripts' / 'rights_reference_signer.py'}")
        assert result.returncode == 1, (name, result.stdout)
        assert "FAIL" in result.stdout


def test_a_wrong_pinned_version_fails():
    result = _conformance(f"{sys.executable} scripts/rights_reference_signer.py",
                          "--expect-version", str(MANIFEST["version"] + 1))
    assert result.returncode == 1
    assert "pinned" in result.stdout
