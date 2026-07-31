#!/bin/bash
# EiraOS — Cognitive Overlay Installer for Ubuntu 24.04 LTS
set -e

echo "=== EiraOS 2.0 — Installing Cognitive Overlay on Ubuntu 24.04 LTS ==="

# Check root
if [ "$EUID" -ne 0 ]; then
  echo "Fejl: Kør venligst som root (sudo ./install.sh)"
  exit 1
fi

# Create eira user & system directories
id -u eira &>/dev/null || useradd -r -m -s /bin/false eira
mkdir -p /opt/eiraos /run/eira /etc/eiraos
chown -R eira:eira /opt/eiraos /run/eira /etc/eiraos

# Copy application files
cp -r app veritas-shield contracts /opt/eiraos/

# Install systemd service units
cp packaging/systemd/*.service /etc/systemd/system/
systemctl daemon-reload

# Enable and start all 7 EiraOS Core Daemons
for daemon in identityd walletd veritasd graphd presenced contextd intentd; do
    echo "Aktiverer eira-${daemon}.service..."
    systemctl enable "eira-${daemon}.service"
    systemctl restart "eira-${daemon}.service" || true
done

echo "=== EiraOS Cognitive Overlay er nu fuldt installeret på Ubuntu! ==="
