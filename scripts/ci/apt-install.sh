#!/usr/bin/env bash
# CI only: apt-get update + install, retried on network trouble.
#
# GitHub's runners sometimes lose DNS for minutes or see a stale mirror index:
# "apt-get update" then succeeds with warnings and every install fails with
# "Unable to locate package" or 404. The update must fail on any error
# (--error-on=any), and the pair is retried with growing pauses.
#
# Usage: scripts/ci/apt-install.sh PACKAGE...   (runs apt-get via sudo if not root)
set -euo pipefail

[[ $# -gt 0 ]] || { echo "usage: $0 PACKAGE..." >&2; exit 64; }
SUDO=()
[[ $(id -u) -eq 0 ]] || SUDO=(sudo)
# Short per-try limits: when the runners cannot reach Ubuntu's mirrors at all
# (seen 11 Nov 2026: every InRelease timed out after 20 s, five apt retries
# each), long apt retries turn one job into an hour. Fail fast, retry here.
APT=("${SUDO[@]}" env DEBIAN_FRONTEND=noninteractive apt-get
     -o Acquire::Retries=1 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20)

for attempt in 1 2 3 4 5 6; do
    if timeout 300 "${APT[@]}" update -q --error-on=any \
        && timeout 900 "${APT[@]}" install -y --no-install-recommends "$@"; then
        exit 0
    fi
    if [[ $attempt -eq 6 ]]; then
        echo "apt failed six times; resolv.conf:" >&2
        cat /etc/resolv.conf >&2 || true
        exit 1
    fi
    echo "apt attempt $attempt failed; retrying" >&2
    sleep $((attempt * 20))
done
