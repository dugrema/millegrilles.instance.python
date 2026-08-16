#!/bin/env bash
set -euo pipefail
# ==============================================================================
# MilleGrilles Installation Script v2
# This version is designed for user-space execution without Docker.
# It avoids creating system users/groups and minimizes sudo requirements.
# ==============================================================================

REPO_ROOT="${REPO_ROOT}" || "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REP_ETC="${REPO_ROOT}/etc"
export REP_BIN="${REPO_ROOT}/bin"

# Defaults
INSTANCE_NAME="$(hostname -s)"
INSTANCE_DOMAIN="$(hostname -f)"
MILLEGRILLES_ROOT="${HOME}/.local/${INSTANCE_NAME}"
TYPE="public"
FICHE_URL=""

# Parse arguments
usage() {
  echo "Usage: $0 [options]"
  echo ""
  echo "Options:"
  echo "  --prefix <path>    Set the installation directory (default: ${HOME}/${INSTANCE_NAME})"
  echo "  --name <name>      Set the instance name (default: ${INSTANCE_NAME})"
  echo "  --domain <domain>  Set the instance domain name (default: ${INSTANCE_DOMAIN})"
  echo "  --type <type>      Installation type: public, prive, protege, secure (default: protege)"
  echo "  --fiche <url>      URL of the fiche file (required)"
  echo "  --help             Display this help message"
  exit 0
}

while [[ "$#" -gt 0 ]]; do
  case $1 in
    --prefix) MILLEGRILLES_ROOT="$2"; shift ;;
    --name) INSTANCE_NAME="$2"; shift ;;
    --domain) INSTANCE_DOMAIN="$2"; shift ;;
    --fiche) FICHE_URL="$2"; shift ;;
    --type) TYPE="$2"; shift ;;
    --help) usage; exit 1 ;;
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
  if [ -f "${MILLEGRILLES_ROOT}/etc/fiche_env" ]; then
    source "${MILLEGRILLES_ROOT}/etc/fiche_env"
  else
    echo "[ERROR] fiche_env not found. Did you run process_fiche_file?"
    exit 1
  fi

  # Prefer using /var/www/html for nginx html content, fallback to user dir when not available
  if [ -d "/var/www/html" ] && [ -w "/var/www/html" ]; then
    MOUNT_NGINX_HTML="/var/www/html"
  else
    MOUNT_NGINX_HTML="${MILLEGRILLES_ROOT}/var/nginx/html"
  fi

  {
    echo "INSTANCE_ID=\"${INSTANCE_ID}\""
    echo "CONTAINER_UID=\"${CONTAINER_UID}\""
    echo "CONTAINER_GID=\"${CONTAINER_GID}\""
    echo "MILLEGRILLES_ROOT=\"${MILLEGRILLES_ROOT}\""
    echo "INSTANCE_NAME=\"${INSTANCE_NAME}\""
    echo "INSTANCE_DOMAIN=\"${INSTANCE_DOMAIN}\""
    echo "MANAGER_URL=\"https://localhost:2443\""
    echo "SECURITE=\"${SECURITE}\""
    echo "MQ_HOSTNAME=${MQ_HOSTNAME}"
    echo "MQ_PORT=${MQ_PORT}"
    echo "MTLS_PORT=${MTLS_PORT}"
    echo "IDMG=${IDMG}"
    echo "MOUNT_FILEHOST=\"${MILLEGRILLES_ROOT}/var/filehost\""
    echo "MOUNT_NGINX_HTML=\"${MOUNT_NGINX_HTML}\""
  } > "${MILLEGRILLES_ROOT}/config.env"

  # Source the newly created config
  source "${MILLEGRILLES_ROOT}/config.env"

  echo "[INFO] Loaded new config.env"
  echo "-----------------------"
  cat "${MILLEGRILLES_ROOT}/config.env"
  echo "-----------------------"

  # Define essential paths relative to MILLEGRILLES_ROOT
  export PATH_MILLEGRILLES="${MILLEGRILLES_ROOT}"
  export PATH_LOGS="${MILLEGRILLES_ROOT}/logs"
  export PATH_VENV="${MILLEGRILLES_ROOT}/venv"
}

preflight_check() {
  echo "[INFO] Running pre-flight checks..."
  # Check if config.env exists in the target installation directory
  if [ -f "${MILLEGRILLES_ROOT}/config.env" ]; then
    echo "[ERROR] MilleGrilles is already installed at ${MILLEGRILLES_ROOT} (config.env exists)."
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

  # local REP_NGINX="${MILLEGRILLES_ROOT}/var/nginx"

  echo "[INFO] Copier fichier web"
  mkdir -p "$MOUNT_NGINX_HTML"

  cp -vr "$REPO_ROOT/etc/nginx/html/"* "${MOUNT_NGINX_HTML}/"

  # Generate self-signed certificates
  bin/x509/web_selfsigned.sh "${MILLEGRILLES_ROOT}/secrets"

  echo "[OK] Fichier web copie"
}

creer_repertoires() {
  echo "[INFO] Configurer les repertoires de MilleGrilles"
  mkdir -p "${MILLEGRILLES_ROOT}/bin"

  mkdir -p "${MILLEGRILLES_ROOT}/secrets"
  chmod 700 "${MILLEGRILLES_ROOT}/secrets"

  mkdir -p "${MILLEGRILLES_ROOT}/var/nginx/html"
  mkdir -p "${MILLEGRILLES_ROOT}/etc/nginx/applications"
  mkdir -p "${MILLEGRILLES_ROOT}/var/nginx/html"

  echo "[OK] Repertoires crees"
}

copier_fichiers() {
  echo "[INFO] Copier fichiers systeme"
  cp -vr "${REPO_ROOT}/bin" "${MILLEGRILLES_ROOT}/"

  if [ "$TYPE" != "secure" ]; then
    cp -iv "${REP_ETC}/nginx/config/"* "${MILLEGRILLES_ROOT}/etc/nginx"
  fi

  echo "[OK] Fichiers copies"
}

configurer_reps() {
  creer_repertoires
  copier_fichiers
}

process_fiche_file() {
  if [ -z "$FICHE_URL" ]; then
    echo "[ERROR] --fiche <url> is required for type $TYPE"
    exit 1
  fi

  echo "[INFO] Downloading fiche from $FICHE_URL"
  mkdir -p "${MILLEGRILLES_ROOT}/etc"
  curl -sL --insecure "$FICHE_URL" -o "${MILLEGRILLES_ROOT}/etc/fiche.json"

  if [ ! -s "${MILLEGRILLES_ROOT}/etc/fiche.json" ]; then
    echo "[ERROR] Failed to download fiche.json or file is empty."
    exit 1
  fi

  echo "[INFO] Extracting information from fiche.json"
  # Use python3 to parse the JSON
  python3 "${REPO_ROOT}/bin/install/process_fiche.py" "${MILLEGRILLES_ROOT}"

  if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to process fiche.json"
    exit 1
  fi
}

install_instance() {
  echo "[INFO] Preparation d'une instance de base"

  if [ ! -d "${MILLEGRILLES_ROOT}/configuration" ]; then
    configurer_reps

    echo "[INFO] Creer venv python3 sous ${PATH_VENV}"
    install_python_venv "${PATH_VENV}"

    # Create an environment activation script (imports config.env and activates the python venv)
    sed "s|__replace_me__|${MILLEGRILLES_ROOT}|" "${REPO_ROOT}/bin/activate.sh.template" > "${MILLEGRILLES_ROOT}/bin/activate.sh" && \
      chmod 755 "${MILLEGRILLES_ROOT}/bin/activate.sh"

    echo "[INFO] Installer millegrilles_instance en mode editable"
    "${PATH_VENV}/bin/pip" install -e .

    echo "[INFO] Copier fichiers de configuration, code python"
    install_web_files
  else
    echo "[WARN] Dossier configuration déjà existant. Installation ignorée."
  fi
}

install_public_instance() {
  echo "[INFO] Starting Public installation..."

  install_instance
  source "${MILLEGRILLES_ROOT}/config.env"

  echo "[INFO] Copying protege level nginx files"
  cp -iv "${REP_ETC}/nginx/nginx_prive/"* "${MILLEGRILLES_ROOT}/etc/nginx"

  echo "[INFO] Requesting Node Manager Certificate..."
  "${PATH_VENV}/bin/python3" bin/x509/request_satellite.py

  # Initialize the local filehost repository
  mkdir -p "${MILLEGRILLES_ROOT}/var/filehost/files/${IDMG}"

  echo "[INFO] Preparing node systemd configuration files for secure"
  ./bin/install/setup_systemd_public.sh "${MILLEGRILLES_ROOT}/config.env"

  echo "[INFO] Start manager"
  systemctl --user restart "${INSTANCE_NAME}-manager"

  echo "[OK] Secure installation complete."
}


# ------------------------------------------------------------------------------
# Main Execution
# ------------------------------------------------------------------------------

main() {
  preflight_check

  process_fiche_file
  save_configenv

  case $TYPE in
    public)
      install_public_instance
      ;;
    *)
      echo "[ERROR] Invalid type: $TYPE"
      usage
      exit 1
      ;;
  esac

  echo
  echo "[INFO] Installation path:  $MILLEGRILLES_ROOT."
  echo "[INFO] Pour permettre aux services de demarrer au boot, utiliser \"sudo loginctl enable-linger $(whoami)\""
  echo "[OK] Installation $TYPE completee avec succès."
}

main
