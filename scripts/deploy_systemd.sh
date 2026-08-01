#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this deployment script as root (for example: sudo $0)." >&2
    exit 1
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
INSTALL_ROOT=${EIRA_INSTALL_ROOT:-/usr/lib/eira-os}
UNIT_SOURCE=${REPO_ROOT}/systemd
UNIT_DEST=/etc/systemd/system

groupadd --system --force eira
if ! id --user eira >/dev/null 2>&1; then
    useradd --system --gid eira --home-dir "${INSTALL_ROOT}" \
        --shell /usr/sbin/nologin eira
fi

install -d -o root -g eira -m 0750 "${INSTALL_ROOT}"
if [[ $(realpath -m "${REPO_ROOT}") != $(realpath -m "${INSTALL_ROOT}") ]]; then
    for runtime_path in app requirements.txt; do
        if [[ -e ${REPO_ROOT}/${runtime_path} ]]; then
            cp -a "${REPO_ROOT}/${runtime_path}" "${INSTALL_ROOT}/"
        fi
    done
fi

chown -R root:eira "${INSTALL_ROOT}"
chmod -R go-w "${INSTALL_ROOT}"
install -d -o eira -g eira -m 0770 \
    /run/eira /var/log/eira /var/lib/eira /data /data/eira-fleet

install -d -o root -g eira -m 0750 /etc/eira
install -d -o root -g root -m 0755 /etc/eira/trust /etc/apparmor.d
if [[ ! -e /etc/eira/eira.conf ]]; then
    umask 0027
    EIRA_GENERATED_TOKEN=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    install -o root -g eira -m 0640 /dev/null /etc/eira/eira.conf
    echo "EIRA_IPC_TOKEN=${EIRA_GENERATED_TOKEN}" > /etc/eira/eira.conf
fi

for daemon in stated identityd fleetd veritasd intentd graphd; do
    install -o root -g root -m 0755 "${REPO_ROOT}/packaging/bin/eira-daemon" \
        "/usr/bin/eira-${daemon}"
done

install -o root -g root -m 0755 "${REPO_ROOT}/packaging/session/eira-session" \
    /usr/bin/eira-session
install -d -o root -g root -m 0755 /usr/share/xsessions
install -o root -g root -m 0644 \
    "${REPO_ROOT}/packaging/session/eira-session.desktop" \
    /usr/share/xsessions/eira-session.desktop
install -o root -g root -m 0644 "${REPO_ROOT}"/packaging/apparmor/usr.bin.eira-* \
    /etc/apparmor.d/

install -o root -g root -m 0644 "${UNIT_SOURCE}"/eira-*.service "${UNIT_DEST}/"
install -o root -g root -m 0644 "${UNIT_SOURCE}/eira.target" "${UNIT_DEST}/"

systemctl daemon-reload
if command -v apparmor_parser >/dev/null 2>&1; then
    apparmor_parser -r /etc/apparmor.d/usr.bin.eira-*
fi
systemctl enable --now eira.target

echo "EiraOS systemd services installed and started."
