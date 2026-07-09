#!/bin/env bash
set -euo pipefail

# ==============================================================================
# MilleGrilles Installation Script v2
# This version is designed for user-space execution.
# It avoids creating system users/groups and minimizes sudo requirements.
# ==============================================================================

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REP_ETC="${REPO_ROOT}/etc"
export REP_BIN="${REPO_ROOT}/bin"

# Defaults
INSTANCE_NAME="$(hostname -s)"
INSTANCE_DOMAIN="$(hostname -f)"
MILLEGRILLES_ROOT="${HOME}/.local/${INSTANCE_NAME}"

# Parse arguments
usage() {
  echo "Usage: $0 [options]"
  echo ""
  echo "Options:"
  echo "  --prefix <path>    Set the installation directory (default: ${HOME}/${INSTANCE_NAME})"
  echo "  --name <name>      Set the instance name (default is local domain, e.g. desktop)"
  echo "  --domain <domain>  Set the instance domain name (default: local, e.g. desktop.domain.com)"
  echo "  --help             Display this help message"
  exit 0
}

while [[ "$#" -gt 0 ]]; do
  case $1 in
    --prefix) MILLEGRILLES_ROOT="$2"; shift ;;
    --name) INSTANCE_NAME="$2"; shift ;;
    --domain) INSTANCE_DOMAIN="$2"; shift ;;
    --help) usage ;;
    *) echo "Unknown parameter: $1"; usage; exit 1 ;;
  esac
  shift
done

export MILLEGRILLES_ROOT
export INSTANCE_NAME
export INSTANCE_DOMAIN
export REPO_ROOT="${REPO_ROOT}"

# Ensure installation directory exists
mkdir -p "${MILLEGRILLES_ROOT}"

# Generate instance-specific config.env
INSTANCE_ID=$(python3 -c 'import uuid; print(uuid.uuid1())')

cat <<EOF > "${MILLEGRILLES_ROOT}/config.env"
INSTANCE_ID="${INSTANCE_ID}"
MILLEGRILLES_ROOT="${MILLEGRILLES_ROOT}"
INSTANCE_NAME="${INSTANCE_NAME}"
INSTANCE_DOMAIN="${INSTANCE_DOMAIN}"
REPO_ROOT="${REPO_ROOT}"
HTTP_PORT=80
HTTPS_PORT=443
HTTPS_MG_PORT=444
MQ_PORT=5673
EOF

# Source the newly created config
source "${MILLEGRILLES_ROOT}/config.env"

# Define essential paths relative to MILLEGRILLES_ROOT
export PATH_MILLEGRILLES="${MILLEGRILLES_ROOT}"
export PATH_LOGS="${MILLEGRILLES_ROOT}/logs"
export PATH_VENV="${MILLEGRILLES_ROOT}/venv"

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

install_python_venv() {
  local PATH_VENV=$1
  echo "[INFO] Configurer venv python3, venv et dependances sous ${PATH_VENV}"
  python3 -m venv --system-site-packages "$PATH_VENV"

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
}

install_web_files() {
  # Source the instance-specific config
  if [ -f "${MILLEGRILLES_ROOT}/config.env" ]; then
      source "${MILLEGRILLES_ROOT}/config.env"
  fi

  local REP_NGINX="${MILLEGRILLES_ROOT}/var/nginx"

  echo "[INFO] Copier fichier web"
  mkdir -p "$REP_NGINX/html"

  cp -vr "$REPO_ROOT/etc/nginx/html" "$REP_NGINX/"

  echo "[OK] Fichier web copie"
}

creer_repertoires() {
  echo "[INFO] Configurer les repertoires de MilleGrilles"
  mkdir -p "${MILLEGRILLES_ROOT}/bin"
  mkdir -p "${MILLEGRILLES_ROOT}/etc/secrets/issuer"
  mkdir -p "${MILLEGRILLES_ROOT}/etc/nginx"
  mkdir -p "${MILLEGRILLES_ROOT}/var/mq"
  mkdir -p "${MILLEGRILLES_ROOT}/var/mongo"
  mkdir -p "${MILLEGRILLES_ROOT}/var/nginx/html"
  mkdir -p "${MILLEGRILLES_ROOT}/var/files"

  echo "[OK] Repertoires crees"
}

copier_fichiers() {
  echo "[INFO] Copier fichiers systeme"
  cp -v "${REP_BIN}/start_instance.sh" "${MILLEGRILLES_ROOT}/bin/"
  cp -v "${REP_ETC}/idmg_validation.json" "${MILLEGRILLES_ROOT}/etc/"
  cp -vr "${REP_ETC}/compose" "${MILLEGRILLES_ROOT}/etc/"
  cp -v "${REP_ETC}/nginx/nginx_installation/"* "${MILLEGRILLES_ROOT}/etc/nginx"

  echo "[OK] Fichiers copies"
}

configurer_reps() {
  creer_repertoires
  copier_fichiers
}

configurer_docker_network() {
  echo "[INFO] Configurer docker pour instance: ${INSTANCE_NAME}"
  # Attempt to initialize swarm if not already in a swarm
  # docker swarm init --advertise-addr 127.0.0.1 > /dev/null 2>&1 || true
  
  docker network create -d overlay --attachable --scope swarm "${INSTANCE_NAME}_net" > /dev/null 2>&1 || true
  # docker config rm docker.versions > /dev/null 2>&1 || true
  
  echo "[OK] Configuration docker swarm completee"
}

install_instance_v2() {
  echo "[INFO] Preparation d'une instance de base"

  if [ ! -d "${MILLEGRILLES_ROOT}/configuration" ]; then
    configurer_reps
    
    echo "[INFO] Creer venv python3 sous ${PATH_VENV}"
    install_python_venv "${PATH_VENV}"
    
    # Install the current package in editable mode so it's importable
    echo "[INFO] Installer millegrilles_instance en mode editable"
    "${PATH_VENV}/bin/pip" install -e .

    echo "[INFO] Copier fichiers de configuration, code python"
    "${REP_BIN}/install_catalogues.sh"
    install_web_files
    configurer_docker_network
  else
    echo "[WARN] Dossier configuration déjà existant. Installation ignorée."
  fi
}

# ------------------------------------------------------------------------------
# Main Execution
# ------------------------------------------------------------------------------

main() {
  preflight_check

  # Init submodules
  if ! [ -d "${REPO_ROOT}/etc/catalogues/signed" ]; then
    echo "Init submodule etc/catalogues"
    git submodule init etc/catalogues
    git submodule update --recursive
  fi

  install_instance_v2

  echo
  echo "[OK] Installation v2 completee avec succès."
}

main
