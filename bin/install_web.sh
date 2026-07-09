#!/bin/bash
set -euo pipefail

# Source the instance-specific config
if [ -f "${MILLEGRILLES_ROOT}/config.env" ]; then
    source "${MILLEGRILLES_ROOT}/config.env"
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
REP_SRC="${REPO_ROOT}/dist/web"
REP_NGINX="${MILLEGRILLES_ROOT}/nginx"

echo "[INFO] Copier fichier web"
mkdir -p "$REP_NGINX"/html

cp -vr "$REPO_ROOT/etc/nginx/html" "$REP_NGINX/"
cp -v "$REP_SRC/favicon.ico" "$REP_NGINX/html"

echo "[OK] Fichier web copie"
