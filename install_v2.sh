#!/bin/env bash
set -euo pipefail

# ==============================================================================
# MilleGrilles Installation Script v2
# This version is designed for user-space execution.
# It avoids creating system users/groups and minimizes sudo requirements.
# ==============================================================================

export REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REP_ETC="${REPO_ROOT}/etc"
export REP_BIN="${REPO_ROOT}/bin"

# Defaults
export INSTANCE_NAME="default"
export MILLEGRILLES_HOME="${HOME}/${INSTANCE_NAME}"
export MG_INSTALL=1

# Parse arguments
while [[ "$#" -gt 0 ]]; do
  case $1 in
    --prefix) MILLEGRILLES_HOME="$2"; shift ;;
    --name) INSTANCE_NAME="$2"; shift ;;
    *) echo "Unknown parameter: $1"; exit 1 ;;
  esac
  shift
done

export MILLEGRILLES_HOME
export INSTANCE_NAME

# Ensure installation directory exists
mkdir -p "${MILLEGRILLES_HOME}"

# Generate instance-specific config.env
cat <<EOF > "${MILLEGRILLES_HOME}/config.env"
MILLEGRILLES_HOME="${MILLEGRILLES_HOME}"
INSTANCE_NAME="${INSTANCE_NAME}"
EOF

# Source the newly created config
source "${MILLEGRILLES_HOME}/config.env"

# Define essential paths relative to MILLEGRILLES_HOME
export PATH_MILLEGRILLES="${MILLEGRILLES_HOME}"
export PATH_LOGS="${MILLEGRILLES_HOME}/logs"
export PATH_VENV="${MILLEGRILLES_HOME}/venv"

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------

preflight_check() {
  echo "[INFO] Running pre-flight checks..."
  if ! command -v git >/dev/null 2>&1; then
    echo "[ERROR] git is not installed."
    exit 1
  fi
  if ! command -v dpkg >/dev/null 2>&1; then
    echo "[ERROR] dpkg is not installed. This script requires a Debian-based system."
    exit 1
  fi
  echo "[OK] Pre-flight checks passed."
}

# ------------------------------------------------------------------------------
# Installation Components (Extracted from original scripts)
# ------------------------------------------------------------------------------

creer_repertoires() {
  echo "[INFO] Configurer les repertoires de MilleGrilles"
  mkdir -p "${MILLEGRILLES_HOME}/issuer" "${PATH_LOGS}"
  mkdir -p "${MILLEGRILLES_HOME}/configuration"
  mkdir -p "${MILLEGRILLES_HOME}/consignation"
  mkdir -p "${MILLEGRILLES_HOME}/nginx/html"
  mkdir -p "${MILLEGRILLES_HOME}/secrets"
  mkdir -p "${MILLEGRILLES_HOME}/shared_secrets"
  mkdir -p "${MILLEGRILLES_HOME}/python"
  mkdir -p "${MILLEGRILLES_HOME}/bin"
  
  echo "[OK] Repertoires crees"
}

copier_fichiers() {
  echo "[INFO] Copier fichiers systeme"
  cp "${REP_BIN}/start_instance.sh" "${MILLEGRILLES_HOME}/bin/" || true
  cp "${REP_ETC}/idmg_validation.json" "${MILLEGRILLES_HOME}/configuration/" || true
  
  # Create an empty config.json to prevent errors in ConfigurationInstance.load()
  if [ ! -f "${MILLEGRILLES_HOME}/configuration/config.json" ]; then
    echo "{}" > "${MILLEGRILLES_HOME}/configuration/config.json"
  fi

  echo "[OK] Fichiers copies"
}

configurer_reps() {
  creer_repertoires
  copier_fichiers
}

configurer_docker_swarm() {
  echo "[INFO] Configurer docker swarm pour instance: ${INSTANCE_NAME}"
  # Attempt to initialize swarm if not already in a swarm
  docker swarm init --advertise-addr 127.0.0.1 > /dev/null 2>&1 || true
  
  docker network create -d overlay --attachable --scope swarm millegrille_net > /dev/null 2>&1 || true
  docker config rm docker.versions > /dev/null 2>&1 || true

  # Config files for Docker Swarm
  # We look for docker.xxx.json files in the docker config directory
  local DOCKER_CONFIG_DIR="${REP_ETC}/docker"
  if [ -d "${DOCKER_CONFIG_DIR}" ]; then
    for FILE in "${DOCKER_CONFIG_DIR}"/docker.*.json; do
      [ -e "$FILE" ] || continue
      local NOM_FICHIER=$(basename "$FILE")
      local MODULE=$(echo "$NOM_FICHIER" | sed 's/^docker\.//;s/\.json$//')
      
      echo "[INFO] Configurer module docker: $MODULE"
      
      docker config rm "docker.cfg.${MODULE}.${INSTANCE_NAME}" > /dev/null 2>&1 || true
      
      local TEMP_CONFIG=$(mktemp)
      # Inject instance name into volume source paths
      sed 's/"source": "\([^"]*\)"/"source": "\1-${INSTANCE_NAME}"/g' "$FILE" > "$TEMP_CONFIG"
      
      docker config create "docker.cfg.${MODULE}.${INSTANCE_NAME}" "$TEMP_CONFIG"
      rm "$TEMP_CONFIG"
    done
  fi
  echo "[OK] Configuration docker swarm completee"
}

install_instance_v2() {
  echo "[INFO] Preparation d'une instance de base"

  if [ ! -d "${MILLEGRILLES_HOME}/configuration" ]; then
    configurer_reps

    echo "[INFO] Creer venv python3 sous ${PATH_VENV}"
    cd "${REPO_ROOT}"
    "${REP_BIN}/install_python.sh" "${PATH_VENV}"
    
    # Install the current package in editable mode so it's importable
    echo "[INFO] Installer millegrilles_instance en mode editable"
    "${PATH_VENV}/bin/pip" install -e .

    echo "[INFO] Copier fichiers de configuration, code python"
    "${REP_BIN}/install_catalogues.sh"
    "${REP_BIN}/install_web.sh"

    if docker info > /dev/null 2>&1; then
      echo "[INFO] Configuration docker détectée"
      configurer_docker_swarm
    fi
  else
    echo "[WARN] Dossier configuration déjà existant. Installation ignorée."
  fi
}

install_fixes_v2() {
  if [ -d "${MILLEGRILLES_HOME}/nginx/html" ]; then
    echo "[INFO] Cleaning up existing nginx/html directory"
    rm -rf "${MILLEGRILLES_HOME}/nginx/html"
    mkdir -p "${MILLEGRILLES_HOME}/nginx/html"
  fi
}

# ------------------------------------------------------------------------------
# Main Execution
# ------------------------------------------------------------------------------

main() {
  preflight_check

  if [ -n "${DEV:-}" ]; then
    export DEV="${DEV}"
  fi

  # Init submodules
  if ! [ -d "${REPO_ROOT}/etc/catalogues/signed" ]; then
    echo "Init submodule etc/catalogues"
    git submodule init etc/catalogues
    git submodule update --recursive
  fi

  install_instance_v2
  install_fixes_v2

  echo
  echo "[OK] Installation v2 completee avec succès."
}

main
