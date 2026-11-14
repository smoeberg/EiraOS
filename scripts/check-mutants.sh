#!/usr/bin/env bash
# Every mutant in tests/mutants/*.patch must be caught by at least one of the
# tests its header names: CTX-* (EIRA-CONTEXT testplan §2), GATE-* and IPC-*
# (Gate Kernel and the IPC access classes, UDVIKLINGSPLAN F0c.2). Applies one
# mutant at a time to a throwaway copy of the source and runs those tests
# there; fails if a mutant survives, if a patch no longer applies
# (regenerate it with tests/mutants/make_mutants.py, never drop it), or if
# the tests could not run at all.
#
# "Caught" means pytest exit status 1: tests ran and one failed. Any other
# non-zero status (2 interrupted or collection error, 3 internal error,
# 4 usage error, 5 no tests collected) means the mutant broke the run, not an
# invariant, and proves nothing (review G-21): the check fails.
#
# Usage: scripts/check-mutants.sh [NAME-OR-GLOB ...]   e.g. 'GATE-*' 'IPC-*' CTX-B1-1
#        (default: all mutants)
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON=${PYTHON:-python3}
cd "$ROOT"

patches=()
if [ "$#" -gt 0 ]; then
    for name in "$@"; do
        matched=0
        for patch in tests/mutants/$name.patch; do
            [ -f "$patch" ] || continue
            patches+=("$patch")
            matched=1
        done
        [ "$matched" -eq 1 ] || { echo "check-mutants: no mutant matches $name" >&2; exit 2; }
    done
else
    patches=(tests/mutants/*.patch)
fi

# The tests must pass without any mutant, or a "caught" mutant proves nothing.
# shellcheck disable=SC2046
baseline=$(sed -n 's/^Tests: //p' "${patches[@]}" | tr ' ' '\n' | sed 's/::.*//' | sort -u | tr '\n' ' ')
# shellcheck disable=SC2086
"$PYTHON" -m pytest -q -p no:cacheprovider $baseline >/dev/null

survived=0
broken=0
for patch in "${patches[@]}"; do
    name=$(basename "$patch" .patch)
    tests=$(sed -n 's/^Tests: //p' "$patch")
    work=$(mktemp -d -t eira-mutant.XXXXXXXX)
    cp -r app tests tools specs packaging systemd scripts "$work/"
    for file in ruff.toml VERSION pyproject.toml pytest.ini; do
        [ -f "$file" ] && cp "$file" "$work/"
    done
    if ! (cd "$work" && patch -p1 --quiet --forward < "$ROOT/$patch"); then
        echo "MUTANT $name: patch does not apply (regenerate with tests/mutants/make_mutants.py)"
        rm -rf -- "$work"
        exit 2
    fi
    status=0
    # shellcheck disable=SC2086
    (cd "$work" && "$PYTHON" -m pytest -q -x -p no:cacheprovider $tests >"$work/.pytest.log" 2>&1) || status=$?
    case "$status" in
        0)
            echo "MUTANT $name: SURVIVED ($(sed -n '1s/^Mutant [^:]*: //p' "$patch"))"
            survived=1
            ;;
        1)
            echo "MUTANT $name: caught"
            ;;
        *)
            echo "MUTANT $name: BROKE THE RUN (pytest exit $status), proves nothing"
            tail -n 15 "$work/.pytest.log" | sed 's/^/    /'
            broken=1
            ;;
    esac
    rm -rf -- "$work"
done

if [ "$broken" -ne 0 ]; then
    echo "check-mutants: a mutant broke the test run instead of an invariant; fix the mutant" >&2
    exit 2
fi
if [ "$survived" -ne 0 ]; then
    echo "check-mutants: a mutant survived; the tests do not protect that invariant" >&2
    exit 1
fi
echo "check-mutants: all ${#patches[@]} mutants caught"
