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
echo "[INFO] Installing system dependencies (git, sudo, dpkg, gcc, python3-pip, python3-venv, python3-dev)..."
apt update
apt install -y git sudo dpkg gcc python3-pip python3-venv python3-dev curl

echo "[OK] System setup complete."
