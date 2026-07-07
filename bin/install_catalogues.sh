#!/bin/env bash
set -euo pipefail

# Source the instance-specific config
if [ -f "${MILLEGRILLES_HOME}/config.env" ]; then
    source "${MILLEGRILLES_HOME}/config.env"
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
# Use variables if available, otherwise fallback to default for safety
PATH_MILLEGRILLES="${PATH_MILLEGRILLES:-$MILLEGRILLES_HOME}"
PATH_VAR_CONFIGURATION="${PATH_MILLEGRILLES}/configuration"
PATH_VAR_CONFIGURATION_DOCKER="${PATH_VAR_CONFIGURATION}/docker"
PATH_VAR_CONFIGURATION_CATALOGUES="${PATH_VAR_CONFIGURATION}/catalogues"
PATH_VAR_CONFIGURATION_WEBAPPCONFIG="${PATH_VAR_CONFIGURATION}/webappconfig"
PATH_VAR_CONFIGURATION_NGINX="${PATH_MILLEGRILLES}/nginx"
PATH_VAR_NGINX="${PATH_MILLEGRILLES}/nginx"
PATH_VAR_CONFIGURATION_PYTHON="${PATH_MILLEGRILLES}/python"
PATH_DIR_CATALOGUES="${REPO_ROOT}/etc/catalogues/signed"
PATH_DIR_ETC="${REPO_ROOT}/etc"
PATH_DIR_DOCKER="${REPO_ROOT}/etc/docker"
PATH_DIR_WEBAPPCONFIG="${REPO_ROOT}/etc/webappconfig"
PATH_DIR_NGINX="${REPO_ROOT}/etc/nginx"
PATH_DIR_INSTANCE="${REPO_ROOT}/millegrilles_instance"

echo "[INFO] Copier fichiers de configuration"

mkdir -p "${PATH_VAR_CONFIGURATION_DOCKER}"
cp -v "${PATH_DIR_DOCKER}"/docker.*.json "${PATH_VAR_CONFIGURATION_DOCKER}" 2>/dev/null || true

mkdir -p "${PATH_VAR_CONFIGURATION_CATALOGUES}"
cp -v "${PATH_DIR_CATALOGUES}"/*.json.xz "${PATH_VAR_CONFIGURATION_CATALOGUES}/" 2>/dev/null || true

mkdir -p "${PATH_VAR_CONFIGURATION_WEBAPPCONFIG}"
cp -v "${PATH_DIR_WEBAPPCONFIG}"/*.json "${PATH_VAR_CONFIGURATION_WEBAPPCONFIG}/" 2>/dev/null || true

mkdir -p "${PATH_VAR_CONFIGURATION_NGINX}"
cp -rv "${PATH_DIR_NGINX}/" "${PATH_VAR_CONFIGURATION_NGINX}/" 2>/dev/null || true
cp -rv "${PATH_DIR_NGINX}/html/" "${PATH_VAR_NGINX}/" 2>/dev/null || true

# Copier la validation
cp "${PATH_DIR_ETC}/idmg_validation.json" "${PATH_VAR_CONFIGURATION}/" 2>/dev/null || true

echo "[INFO] Copier python instance"
mkdir -p "${PATH_VAR_CONFIGURATION_PYTHON}"
if [ -d "${PATH_DIR_INSTANCE}" ]; then
    cp -rv "${PATH_DIR_INSTANCE}/." "${PATH_VAR_CONFIGURATION_PYTHON}/"
fi

echo "[OK] Fichier configurations copies OK"
