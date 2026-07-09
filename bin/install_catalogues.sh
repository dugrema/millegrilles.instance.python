#!/bin/env bash
set -euo pipefail

# Source the instance-specific config
if [ -f "${MILLEGRILLES_ROOT}/config.env" ]; then
    source "${MILLEGRILLES_ROOT}/config.env"
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
# Use variables if available, otherwise fallback to default for safety
PATH_VAR_CONFIGURATION="${MILLEGRILLES_ROOT}/etc"
PATH_VAR_CONFIGURATION_DOCKER="${PATH_VAR_CONFIGURATION}/docker"
PATH_VAR_CONFIGURATION_CATALOGUES="${PATH_VAR_CONFIGURATION}/catalogues"
PATH_VAR_CONFIGURATION_WEBAPPCONFIG="${PATH_VAR_CONFIGURATION}/webappconfig"
PATH_DIR_CATALOGUES="${REPO_ROOT}/etc/catalogues/signed"
PATH_DIR_ETC="${REPO_ROOT}/etc"
PATH_DIR_DOCKER="${REPO_ROOT}/etc/docker"
PATH_DIR_WEBAPPCONFIG="${REPO_ROOT}/etc/webappconfig"

echo "[INFO] Copier fichiers de configuration"

mkdir -p "${PATH_VAR_CONFIGURATION_DOCKER}"
cp -vr "${PATH_DIR_DOCKER}"/compose "${PATH_VAR_CONFIGURATION_DOCKER}" 2>/dev/null || true

mkdir -p "${PATH_VAR_CONFIGURATION_CATALOGUES}"
cp -v "${PATH_DIR_CATALOGUES}"/*.json.xz "${PATH_VAR_CONFIGURATION_CATALOGUES}/" 2>/dev/null || true

mkdir -p "${PATH_VAR_CONFIGURATION_WEBAPPCONFIG}"
cp -v "${PATH_DIR_WEBAPPCONFIG}"/*.json "${PATH_VAR_CONFIGURATION_WEBAPPCONFIG}/" 2>/dev/null || true

# Copier la validation
cp "${PATH_DIR_ETC}/idmg_validation.json" "${PATH_VAR_CONFIGURATION}/" 2>/dev/null || true

echo "[OK] Fichier configurations copies OK"
