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
TYPE="protege"

# Parse arguments
usage() {
  echo "Usage: $0 [options]"
  echo ""
  echo "Options:"
  echo "  --prefix <path>    Set the installation directory (default: ${HOME}/${INSTANCE_NAME})"
  echo "  --name <name>      Set the instance name (default: ${INSTANCE_NAME})"
  echo "  --domain <domain>  Set the instance domain name (default: ${INSTANCE_DOMAIN})"
  echo "  --type <type>      Installation type: public, prive, protege, secure (default: protege)"
  echo "  --help             Display this help message"
  exit 0
}

while [[ "$#" -gt 0 ]]; do
  case $1 in
    --prefix) MILLEGRILLES_ROOT="$2"; shift ;;
    --name) INSTANCE_NAME="$2"; shift ;;
    --domain) INSTANCE_DOMAIN="$2"; shift ;;
    --type) TYPE="$2"; shift ;;
    --help) usage ;;
    *) echo "Unknown parameter: $1"; usage; exit 1 ;;
  esac
  shift
done

export MILLEGRILLES_ROOT
export INSTANCE_NAME
export INSTANCE_DOMAIN
export REPO_ROOT="${REPO_ROOT}"
export TYPE

# Ensure installation directory exists
mkdir -p "${MILLEGRILLES_ROOT}"

# Generate instance-specific config.env
INSTANCE_ID=$(python3 -c 'import uuid; print(uuid.uuid1())')
CONTAINER_UID=$(id -u)
CONTAINER_GID=$(id -g)

case $TYPE in
  public) SECURITE="1.public" ;;
  prive) SECURITE="2.prive" ;;
  protege) SECURITE="3.protege" ;;
  secure) SECURITE="4.secure" ;;
  *) echo "[ERROR] Invalid type: $TYPE"; usage; exit 1 ;;
esac

save_configenv() {
  cat <<EOF > "${MILLEGRILLES_ROOT}/config.env"
INSTANCE_ID="${INSTANCE_ID}"
CONTAINER_UID="${CONTAINER_UID}"
CONTAINER_GID="${CONTAINER_GID}"
MILLEGRILLES_ROOT="${MILLEGRILLES_ROOT}"
INSTANCE_NAME="${INSTANCE_NAME}"
INSTANCE_DOMAIN="${INSTANCE_DOMAIN}"
REPO_ROOT="${REPO_ROOT}"
HTTP_PORT=80
HTTPS_PORT=443
HTTPS_MG_PORT=444
MANAGER_URL="https://localhost:2443"
CERTISSUER_URL="http://localhost:2080"
REDIS_URL=""
SECURITE="${SECURITE}"
EOF

  # Source the newly created config
  source "${MILLEGRILLES_ROOT}/config.env"

  # Define essential paths relative to MILLEGRILLES_ROOT
  export PATH_MILLEGRILLES="${MILLEGRILLES_ROOT}"
  export PATH_LOGS="${MILLEGRILLES_ROOT}/logs"
  export PATH_VENV="${MILLEGRILLES_ROOT}/venv"
}


# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------

preflight_check() {
  echo "[INFO] Running pre-flight checks..."
  # Check if config.env exists in the target installation directory
  if [ -f "${MILLEGRILLES_ROOT}/config.env" ]; then
    echo "[ERROR] MilleGrilles is already installed at ${MILLEGRILLES_ROOT} (config.env exists)."
    exit 1
  fi
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
  mkdir -p "${MILLEGRILLES_ROOT}/etc/secrets/certissuer"
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
  docker network create -d overlay --attachable --scope swarm "${INSTANCE_NAME}_net" > /dev/null 2>&1 || true
  echo "[OK] Configuration docker network completee"
}

install_instance_v2() {
  echo "[INFO] Preparation d'une instance de base"

  if [ ! -d "${MILLEGRILLES_ROOT}/configuration" ]; then
    configurer_reps
    
    echo "[INFO] Creer venv python3 sous ${PATH_VENV}"
    install_python_venv "${PATH_VENV}"
    
    echo "[INFO] Installer millegrilles_instance en mode editable"
    "${PATH_VENV}/bin/pip" install -e .

    echo "[INFO] Copier fichiers de configuration, code python"
    install_web_files
    configurer_docker_network
  else
    echo "[WARN] Dossier configuration déjà existant. Installation ignorée."
  fi
}

install_protege_instance() {
  echo "[INFO] Starting Protege installation..."
  
  install_instance_v2
  source "${MILLEGRILLES_ROOT}/config.env"

  echo "[INFO] Generating Root CA..."
  local log_file
  log_file=$(mktemp)
  ./bin/ca_new.sh > "$log_file" 2>&1
  
  local password
  password=$(grep "Root CA Password for ${INSTANCE_NAME}:" "$log_file" | sed -E 's/.*: ([^ ]*).*/\1/')
  
  if [ -z "$password" ]; then
    echo "[ERROR] Failed to extract Root CA password from logs."
    cat "$log_file"
    rm -f "$log_file"
    exit 1
  fi
  echo "[INFO] Root CA Password extracted."

  echo "[INFO] Generating Signing CA..."
  ./bin/ca_signing.sh --password "$password"

  echo "[INFO] Generating Node Certificate..."
  "${PATH_VENV}/bin/python3" bin/ca_protege.py \
    --millegrilles-root "${MILLEGRILLES_ROOT}" \
     --instance-id "${INSTANCE_ID}" \
     --ca-pem "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/signing_ca.pem"

  # Activate python venv
  . "${MILLEGRILLES_ROOT}/venv/bin/activate"
  IDMG=$(python3 bin/get_idmg.py "${MILLEGRILLES_ROOT}/etc/millegrille.pem")

  if [ -z "$IDMG" ]; then
    echo "[ERROR] Failed to retrieve IDMG from Root CA."
    exit 1
  fi

  echo "IDMG=$IDMG" >> "${MILLEGRILLES_ROOT}/config.env"

  echo "[OK] Protege installation complete."
  echo
  echo "------------------------------------------------------------------------------"
  echo "Root CA Password: $password"
  echo "------------------------------------------------------------------------------"
  echo "IMPORTANT: Save this password! It is required for future operations."
}

# ------------------------------------------------------------------------------
# Main Execution
# ------------------------------------------------------------------------------

main() {
  preflight_check

  save_configenv

  case $TYPE in
    protege)
      install_protege_instance
      ;;
    public|prive|secure)
      install_instance_v2
      ;;
    *)
      echo "[ERROR] Invalid type: $TYPE"
      usage
      exit 1
      ;;
  esac

  echo
  echo "[INFO] Installation path:  $MILLEGRILLES_ROOT."
  echo "[OK] Installation $TYPE completee avec succès."
}

main
