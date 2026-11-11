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

# The CI image carries every package the install needs (/eira/repo, from
# scripts/build_offline_repo.sh) and installs without network.
OFFLINE_LIST=/etc/apt/sources.list.d/eira-offline.list
# apt's sandbox user must be able to read the local packages.
chmod 0755 "$SRC"
if [ -f "$SRC/repo/Packages.gz" ]; then
    chmod -R a+rX "$SRC/repo"
    echo "deb [trusted=yes] file:$SRC/repo ./" > "$OFFLINE_LIST"
fi

# The installer may leave the target without package lists. Offline, only
# the local repo is read: an unreachable archive would fail the update.
if [ -f "$OFFLINE_LIST" ]; then
    $APT -o Dir::Etc::sourcelist="$OFFLINE_LIST" -o Dir::Etc::sourceparts=- \
        -o APT::Get::List-Cleanup=0 update
else
    $APT update
fi
chmod 0644 "$SRC/eira-os-core.deb" "$SRC/eira-labwc.deb"
# eira-labwc (labwc >= 0.20.3) replaces Ubuntu's labwc; eira-os-core depends on it.
$APT install -y "$SRC/eira-labwc.deb" "$SRC/eira-os-core.deb"
# XWayland for the session (already present when the installer added it).
$APT install -y xwayland
rm -f "$OFFLINE_LIST"

install -D -m 0755 "$SRC/eira-firstboot" /usr/lib/eira/eira-firstboot
install -m 0644 "$SRC/eira-firstboot.service" /etc/systemd/system/eira-firstboot.service

# Kun CI-varianten af ISO'et har en acceptancetest med (scripts/build_iso.sh --ci-unattended).
if [ -x "$SRC/ci/eira-ci-setup" ]; then
    "$SRC/ci/eira-ci-setup" "$SRC/ci"
fi

systemctl enable eira.target
systemctl enable eira-firstboot.service
systemctl set-default graphical.target
