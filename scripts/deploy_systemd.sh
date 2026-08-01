#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this deployment script as root (for example: sudo $0)." >&2
    exit 1
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
INSTALL_ROOT=${EIRA_INSTALL_ROOT:-/opt/eira}
UNIT_SOURCE=${REPO_ROOT}/systemd
UNIT_DEST=/etc/systemd/system

groupadd --system --force eira
if ! id --user eira >/dev/null 2>&1; then
    useradd --system --gid eira --home-dir "${INSTALL_ROOT}" \
        --shell /usr/sbin/nologin eira
fi

install -d -o root -g eira -m 0750 "${INSTALL_ROOT}"
if [[ $(realpath -m "${REPO_ROOT}") != $(realpath -m "${INSTALL_ROOT}") ]]; then
    for runtime_path in app requirements.txt veritas-shield; do
        if [[ -e ${REPO_ROOT}/${runtime_path} ]]; then
            cp -a "${REPO_ROOT}/${runtime_path}" "${INSTALL_ROOT}/"
        fi
    done
fi

chown -R root:eira "${INSTALL_ROOT}"
chmod -R go-w "${INSTALL_ROOT}"
install -d -o eira -g eira -m 0770 \
    /run/eira /var/log/eira /var/lib/eira "${INSTALL_ROOT}/data"

install -o root -g root -m 0644 "${UNIT_SOURCE}"/eira-*.service "${UNIT_DEST}/"
install -o root -g root -m 0644 "${UNIT_SOURCE}/eira.target" "${UNIT_DEST}/"

systemctl daemon-reload
systemctl enable --now eira.target

echo "EiraOS systemd services installed and started."
