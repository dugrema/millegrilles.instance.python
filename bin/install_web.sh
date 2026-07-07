#!/bin/bash
set -euo pipefail

# Source the instance-specific config
if [ -f "${MILLEGRILLES_HOME}/config.env" ]; then
    source "${MILLEGRILLES_HOME}/config.env"
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
PATH_MILLEGRILLES="${PATH_MILLEGRILLES:-$MILLEGRILLES_HOME}"
REP_SRC="${REPO_ROOT}/dist/web"
REP_NGINX_HTML="${PATH_MILLEGRILLES}/nginx/html"
REP_NGINX_DATA="${PATH_MILLEGRILLES}/nginx/data"

echo "[INFO] Copier fichier web"
mkdir -p "$REP_NGINX_HTML" "$REP_NGINX_DATA"
cp "$REP_SRC/favicon.ico" "$REP_NGINX_HTML/" 2>/dev/null || true

echo "[OK] Fichier web copie"
