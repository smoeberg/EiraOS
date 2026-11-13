#!/usr/bin/env bash
# EIRA-CONTEXT testplan §2: every mutant in tests/mutants/CTX-*.patch must be
# caught by at least one of the tests its header names. Applies one mutant at
# a time to a throwaway copy of the source and runs those tests there; fails
# if a mutant survives, or if a patch no longer applies (regenerate it with
# tests/mutants/make_mutants.py, never drop it).
#
# Usage: scripts/check-mutants.sh [CTX-B1-1 ...]   (default: all)
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON=${PYTHON:-python3}
cd "$ROOT"

if [ "$#" -gt 0 ]; then
    patches=()
    for name in "$@"; do patches+=("tests/mutants/$name.patch"); done
else
    patches=(tests/mutants/CTX-*.patch)
fi

# The tests must pass without any mutant, or a "caught" mutant proves nothing.
"$PYTHON" -m pytest -q -p no:cacheprovider tests/context >/dev/null

survived=0
for patch in "${patches[@]}"; do
    name=$(basename "$patch" .patch)
    tests=$(sed -n 's/^Tests: //p' "$patch")
    work=$(mktemp -d -t eira-mutant.XXXXXXXX)
    cp -r app tests tools specs "$work/"
    [ -f ruff.toml ] && cp ruff.toml "$work/"
    if ! (cd "$work" && patch -p1 --quiet --forward < "$ROOT/$patch"); then
        echo "MUTANT $name: patch does not apply (regenerate with tests/mutants/make_mutants.py)"
        rm -rf -- "$work"
        exit 2
    fi
    # shellcheck disable=SC2086
    if (cd "$work" && "$PYTHON" -m pytest -q -x -p no:cacheprovider $tests >/dev/null 2>&1); then
        echo "MUTANT $name: SURVIVED ($(sed -n '1s/^Mutant [^:]*: //p' "$patch"))"
        survived=1
    else
        echo "MUTANT $name: caught"
    fi
    rm -rf -- "$work"
done

if [ "$survived" -ne 0 ]; then
    echo "check-mutants: a mutant survived; the tests do not protect that invariant" >&2
    exit 1
fi
echo "check-mutants: all ${#patches[@]} mutants caught"
