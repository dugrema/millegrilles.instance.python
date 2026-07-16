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

echo "[INFO] Adding user to docker group"
sudo usermod -aG docker "$SUDO_USER"

echo "[INFO] Enabling and restarting Docker..."
systemctl enable docker
systemctl restart docker

echo "[OK] System setup complete."
echo "[INFO] Your user has been added to the 'docker' group, you may have to log out/in to use docker without sudo."
