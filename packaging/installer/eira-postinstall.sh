#!/bin/sh
# EiraOS post-install — kører i det installerede system (curtin in-target).
#
# Installerer eira-os-core, lægger session-konfiguration på plads og aktiverer
# eira-firstboot, som binder den bruger, installeren opretter, til
# EiraOS-sessionen. Brugeren oprettes først af cloud-init ved første boot,
# derfor kan det ikke gøres her.
set -eu

SRC=${EIRA_INSTALL_SRC:-/var/lib/eira-install}
export DEBIAN_FRONTEND=noninteractive

apt-get install -y "$SRC/eira-os-core.deb"

install -d -m 0755 /etc/greetd /etc/labwc
install -m 0644 "$SRC/session/greetd/config.toml" /etc/greetd/config.toml
install -m 0644 "$SRC/session/labwc/rc.xml" /etc/labwc/rc.xml
install -m 0755 "$SRC/session/labwc/autostart" /etc/labwc/autostart

# NetworkManager styrer netværket (Wi-Fi m.m.), ikke systemd-networkd.
install -d -m 0755 /etc/netplan
cat > /etc/netplan/01-eira-network-manager.yaml <<'EOF'
network:
  version: 2
  renderer: NetworkManager
EOF
chmod 0600 /etc/netplan/01-eira-network-manager.yaml

install -D -m 0755 "$SRC/eira-firstboot" /usr/lib/eira/eira-firstboot
install -m 0644 "$SRC/eira-firstboot.service" /etc/systemd/system/eira-firstboot.service

systemctl enable eira.target
systemctl enable eira-firstboot.service
# greetd aktiveres først af eira-firstboot, når brugeren findes.
systemctl disable greetd.service >/dev/null 2>&1 || true
systemctl set-default graphical.target
