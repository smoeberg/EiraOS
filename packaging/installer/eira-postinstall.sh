#!/bin/sh
# EiraOS post-install — kører i det installerede system (curtin in-target).
#
# Ubuntu Desktop er allerede installeret (GDM, NetworkManager, PipeWire,
# UPower osv.). Her lægges EiraOS ovenpå: pakken med daemons, shell og
# Wayland-sessionen, og eira-firstboot, som gør EiraOS til standard-session
# for brugeren fra installeren og giver adgang til daemon-sockets.
set -eu

SRC=${EIRA_INSTALL_SRC:-/var/lib/eira-install}
LOG=${EIRA_POSTINSTALL_LOG:-/var/log/eira-postinstall.log}
export DEBIAN_FRONTEND=noninteractive

# Everything is logged in the installed system for diagnosis.
exec >>"$LOG" 2>&1
echo "== eira-postinstall $(date -u +%FT%TZ)"
set -x

# A slow or flaky network must not fail the install outright: apt retries
# each download and gives up on a stalled connection instead of hanging.
APT="apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60"

# The installer may leave the target without package lists.
$APT update
# apt's sandbox user must be able to read the local package.
chmod 0755 "$SRC"
chmod 0644 "$SRC/eira-os-core.deb"
$APT install -y "$SRC/eira-os-core.deb"

install -D -m 0755 "$SRC/eira-firstboot" /usr/lib/eira/eira-firstboot
install -m 0644 "$SRC/eira-firstboot.service" /etc/systemd/system/eira-firstboot.service

# Kun CI-varianten af ISO'et har en acceptancetest med (scripts/build_iso.sh --ci-unattended).
if [ -x "$SRC/ci/eira-ci-setup" ]; then
    "$SRC/ci/eira-ci-setup" "$SRC/ci"
fi

systemctl enable eira.target
systemctl enable eira-firstboot.service
systemctl set-default graphical.target
