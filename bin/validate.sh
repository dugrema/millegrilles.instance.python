#!/bin/bash
set -euo pipefail

echo "[INFO] Starting validation of MilleGrilles installation..."

# Check Directories
for dir in /var/opt/millegrilles /var/log/millegrilles; do
  if [ ! -d "$dir" ]; then
    echo "[ERROR] Directory $dir does not exist."
    exit 1
  else
    echo "[OK] Directory $dir exists."
  fi
done

# Check Permissions (simplified check)
if [ ! -d /var/opt/millegrilles ]; then
  echo "[ERROR] /var/opt/millegrilles does not exist."
  exit 1
else
  OWNER=$(stat -c '%U:%G' /var/opt/millegrilles)
  if [ "$OWNER" != "mginstance:millegrilles" ]; then
    echo "[WARNING] Incorrect ownership on /var/opt/millegrilles: $OWNER (expected mginstance:millegrilles)"
  else
    echo "[OK] Ownership on /var/opt/millegrilles is correct: $OWNER"
  fi
fi

# Check Service
if systemctl is-active --quiet mginstance.service; then
  echo "[OK] Service mginstance is running."
else
  echo "[WARNING] Service mginstance is not running."
fi

# Check Python Venv
if [ -d "/var/opt/millegrilles/venv" ]; then
  echo "[OK] Python venv exists at /var/opt/millegrilles/venv"
else
  echo "[ERROR] Python venv does not exist at /var/opt/millegrilles/venv"
  exit 1
fi

echo "[INFO] Validation complete."
