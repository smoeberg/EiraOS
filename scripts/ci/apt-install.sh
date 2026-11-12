#!/usr/bin/env bash
# CI only: apt-get update + install, retried, with a fallback mirror.
#
# GitHub's runners sometimes cannot reach Ubuntu's own hosts at all: on
# 11 Nov 2026 *.ubuntu.com stopped resolving or timed out for hours while
# other hosts (packages.microsoft.com) worked. Then "apt-get update" only
# warns and every install fails with "Unable to locate package". So:
#
# * the update must fail on any error (--error-on=any);
# * each try is short (one apt retry, 20 s timeouts, a hard limit), so an
#   outage costs minutes, not an hour;
# * after two failed tries the sources are pointed at a full Ubuntu mirror
#   outside ubuntu.com (MIT, then kernel.org). Trust does not change: apt still verifies every
#   index against Ubuntu's archive key, whichever host serves it.
#
# Usage: scripts/ci/apt-install.sh PACKAGE...   (sudo is used if not root)
set -euo pipefail

[[ $# -gt 0 ]] || { echo "usage: $0 PACKAGE..." >&2; exit 64; }
SUDO=()
[[ $(id -u) -eq 0 ]] || SUDO=(sudo)
APT=("${SUDO[@]}" env DEBIAN_FRONTEND=noninteractive apt-get
     -o Acquire::Retries=1 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20)
read -r -a FALLBACKS <<<"${EIRA_APT_FALLBACK_MIRRORS:-http://mirrors.mit.edu/ubuntu http://mirrors.edge.kernel.org/ubuntu}"
BACKUP=$(mktemp -d)

source_files() {
    local f
    for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.list \
             /etc/apt/sources.list.d/*.sources /etc/apt/apt-mirrors.txt; do
        [[ -f $f ]] && printf '%s\n' "$f"
    done
    return 0
}

use_mirror() {
    local mirror=$1 f saved
    echo "apt: switching Ubuntu sources to $mirror" >&2
    while read -r f; do
        saved="$BACKUP/$(basename "$f").orig"
        [[ -f $saved ]] || cp -- "$f" "$saved"
        sed -E "s#https?://((azure|[a-z]{2})\\.)?archive\\.ubuntu\\.com/ubuntu/?#${mirror}/#g;
                s#https?://security\\.ubuntu\\.com/ubuntu/?#${mirror}/#g" \
            "$saved" | "${SUDO[@]}" tee "$f" >/dev/null
    done < <(source_files)
}

for attempt in 1 2 3 4 5 6; do
    if (( attempt >= 3 )); then
        use_mirror "${FALLBACKS[$(( (attempt - 3) % ${#FALLBACKS[@]} ))]}"
    fi
    if timeout 300 "${APT[@]}" update -q --error-on=any \
        && timeout 1500 "${APT[@]}" install -y --no-install-recommends "$@"; then
        exit 0
    fi
    if [[ $attempt -eq 6 ]]; then
        echo "apt failed six times; resolv.conf:" >&2
        cat /etc/resolv.conf >&2 || true
        exit 1
    fi
    echo "apt attempt $attempt failed; retrying" >&2
    sleep $((attempt * 10))
done
