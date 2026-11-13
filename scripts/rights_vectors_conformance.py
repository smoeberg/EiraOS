#!/usr/bin/env python3
"""Run the shared rights vectors against a signer (UDVIKLINGSPLAN F1.9, S-20).

eira-os proves its verifier with tests/test_rights_set_contract.py. This
script is for the other side: eira-fleet-control runs it in its CI against
its own signer, pinned to a version of the vector set, and so proves that
what Fleet signs is byte for byte what the endpoint verifies.

    scripts/rights_vectors_conformance.py --signer "CMD" [--expect-version N] [--vectors DIR]

CMD reads one JSON request per line on stdin and answers each with the
canonical signed document on one line (see scripts/rights_reference_signer.py).
Exit status 0 only if every vector matches and the set is the pinned version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

DEFAULT_VECTORS = Path(__file__).resolve().parents[1] / "tests" / "vectors"


def _check_manifest(vectors: Path, expect_version: int | None) -> tuple[int, list[str]]:
    manifest = json.loads((vectors / "MANIFEST.json").read_text(encoding="utf-8"))
    problems = []
    for name, digest in manifest["files"].items():
        path = vectors / name
        if not path.is_file():
            problems.append(f"missing {name}")
        elif "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"{name} differs from the manifest")
    if expect_version is not None and manifest["version"] != expect_version:
        problems.append(f"vector set is version {manifest['version']}, pinned {expect_version}")
    return manifest["version"], problems


def run(signer: str, vectors: Path = DEFAULT_VECTORS, expect_version: int | None = None) -> int:
    version, problems = _check_manifest(vectors, expect_version)
    for problem in problems:
        print(f"FAIL manifest: {problem}")
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((vectors / "rights-signing").glob("*.json"))]
    requests = "".join(
        json.dumps({"kind": c["kind"], "seed_hex": c["seed_hex"], "document": c["document"]}, ensure_ascii=False) + "\n"
        for c in cases
    )
    result = subprocess.run(shlex.split(signer), input=requests.encode(), capture_output=True, timeout=120)
    if result.returncode != 0:
        print(f"FAIL signer exited {result.returncode}: {result.stderr.decode(errors='replace')[-2000:]}")
        return 1
    answers = result.stdout.split(b"\n")
    failed = len(problems)
    for index, case in enumerate(cases):
        got = answers[index] if index < len(answers) else b""
        expected = case["expect_raw"].encode()
        if got == expected:
            print(f"PASS {case['name']}")
        else:
            failed += 1
            print(f"FAIL {case['name']}\n  expected {expected[:160]!r}\n  got      {got[:160]!r}")
    print(f"eira-rights-vectors v{version}: {len(cases) - (failed - len(problems))}/{len(cases)} signing vectors match")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--signer", required=True, help="command that signs requests from stdin")
    parser.add_argument("--vectors", type=Path, default=DEFAULT_VECTORS)
    parser.add_argument("--expect-version", type=int)
    args = parser.parse_args(argv)
    return run(args.signer, args.vectors, args.expect_version)


if __name__ == "__main__":
    sys.exit(main())
