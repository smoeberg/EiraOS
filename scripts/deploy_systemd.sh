#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
        exec sudo "$0" "$@"
    fi
    echo "error: deploy_systemd.sh must be run as root or with sudo" >&2
    exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
SYSTEMD_SOURCE="${REPO_ROOT}/systemd"
SYSTEMD_DEST="/etc/systemd/system"

if [[ ! -d "${SYSTEMD_SOURCE}" ]]; then
    echo "error: systemd unit directory not found: ${SYSTEMD_SOURCE}" >&2
    exit 1
fi

groupadd -f eira

if ! getent passwd eira >/dev/null; then
    useradd -r -g eira eira
fi

install -d -m 0770 -o eira -g eira /run/eira
install -d -m 0770 -o eira -g eira /var/log/eira

shopt -s nullglob
units=( "${SYSTEMD_SOURCE}"/* )
if (( ${#units[@]} == 0 )); then
    echo "error: no systemd unit files found in ${SYSTEMD_SOURCE}" >&2
    exit 1
fi

install -m 0644 "${units[@]}" "${SYSTEMD_DEST}/"

systemctl daemon-reload
systemctl enable --now eira.target
