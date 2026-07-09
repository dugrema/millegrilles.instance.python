#!/bin/env bash
set -euo pipefail

# This script handles system-wide configuration and requires sudo.
# It should be run only once per system.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REP_ETC="${REPO_ROOT}/etc"
REP_BIN="${REPO_ROOT}/bin"

# Ensure we are running as root or with sudo
if [ "$(id -u)" -ne 0 ]; then
  echo "[ERROR] This script must be run with sudo."
  exit 1
fi

echo "[INFO] Starting system setup..."

# 1. Install system dependencies
echo "[INFO] Installing system dependencies (git, sudo, dpkg, python3-pip, python3-venv, docker.io)..."
apt update
apt install -y git sudo dpkg python3-pip python3-venv docker.io docker-compose-v2

# 2. Configure Docker
echo "[INFO] Configuring Docker..."
if [ -f "${REP_ETC}/daemon.json" ]; then
  echo "[INFO] Copying daemon.json to /etc/docker/"
  mkdir -p /etc/docker
  cp "${REP_ETC}/daemon.json" /etc/docker/daemon.json
else
  echo "[WARN] ${REP_ETC}/daemon.json not found, skipping."
fi

echo "[INFO] Enabling and restarting Docker..."
systemctl enable docker
systemctl restart docker

# 3. Configure rsyslog if required (Optional, currently commented out in installer)
# echo "[INFO] Configuring rsyslog..."
# cp "${REP_ETC}/01-millegrilles.conf" /etc/rsyslog.d/ || true
# systemctl restart rsyslog

echo "[OK] System setup complete. Please ensure your user is in the 'docker' group."
echo "[INFO] Run 'sudo usermod -aG docker \$USER' and log out/in to use docker without sudo."
