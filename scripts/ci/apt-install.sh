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
APT=("${SUDO[@]}" env DEBIAN_FRONTEND=noninteractive apt-get
     -o Acquire::Retries=5 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60)

for attempt in 1 2 3 4 5 6; do
    if "${APT[@]}" update -q --error-on=any \
        && "${APT[@]}" install -y --no-install-recommends "$@"; then
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
