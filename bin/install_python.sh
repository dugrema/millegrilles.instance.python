#!/bin/env bash
set -euo pipefail

PATH_VENV=$1
# REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[INFO] Configurer venv python3, venv et dependances sous ${PATH_VENV}"
python3 -m venv --system-site-packages $PATH_VENV

echo "Activer venv ${PATH_VENV}"
source "${PATH_VENV}/bin/activate"

if ! pip3 list | grep "wheel" > /dev/null; then
  echo "[INFO] Installer pip wheel"
  pip3 install wheel
fi

echo "[INFO] Verifier requirements python pour millegrilles, installer au besoin"
pip3 install -r "${REPO_ROOT}/requirements.txt"

echo "[INFO] Fix oscrypto pour OpenSSL 3"
OSCRYPTO_ZIP="${REPO_ROOT}/lib/oscrypto_130_fix_d5f3437ed24257895ae1edd9e503cfb352e635a8.zip"
if [ -f "$OSCRYPTO_ZIP" ]; then
  pip3 install "$OSCRYPTO_ZIP"
else
  echo "[WARN] Patched oscrypto not found at $OSCRYPTO_ZIP"
fi

echo "[INFO] Fin configuration venv python3"
