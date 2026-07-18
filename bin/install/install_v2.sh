#!/bin/env bash
set -euo pipefail
# ==============================================================================
# MilleGrilles Installation Script v2
# This version is designed for user-space execution.
# It avoids creating system users/groups and minimizes sudo requirements.
# ==============================================================================

REPO_ROOT="${REPO_ROOT}" || "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REP_ETC="${REPO_ROOT}/etc"
export REP_BIN="${REPO_ROOT}/bin"

# Defaults
INSTANCE_NAME="$(hostname -s)"
INSTANCE_DOMAIN="$(hostname -f)"
MILLEGRILLES_ROOT="${HOME}/.local/${INSTANCE_NAME}"
TYPE="protege"

# Check if all apt packages are installed and docker is available to the user
"${REPO_ROOT}/bin/install/env_check.sh"

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
  MQ_PORT=5673
  MQ_HOSTNAME=localhost

  cat <<EOF > "${MILLEGRILLES_ROOT}/config.env"
INSTANCE_ID="${INSTANCE_ID}"
CONTAINER_UID="${CONTAINER_UID}"
CONTAINER_GID="${CONTAINER_GID}"
MILLEGRILLES_ROOT="${MILLEGRILLES_ROOT}"
INSTANCE_NAME="${INSTANCE_NAME}"
INSTANCE_DOMAIN="${INSTANCE_DOMAIN}"
MANAGER_URL="https://localhost:2443"
CERTISSUER_URL="http://localhost:2080"
REDIS_URL="rediss://localhost:6379"
SECURITE="${SECURITE}"
MQ_PORT=$MQ_PORT
MQ_HOSTNAME=$MQ_HOSTNAME
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

  # Generate self-signed certificates
  bin/x509/web_selfsigned.sh "${MILLEGRILLES_ROOT}/secrets"

  echo "[OK] Fichier web copie"
}

creer_repertoires() {
  echo "[INFO] Configurer les repertoires de MilleGrilles"
  mkdir -p "${MILLEGRILLES_ROOT}/bin"
  mkdir -p "${MILLEGRILLES_ROOT}/etc/nginx"
  mkdir -p "${MILLEGRILLES_ROOT}/secrets/certissuer"
  mkdir -p "${MILLEGRILLES_ROOT}/var/mq"
  mkdir -p "${MILLEGRILLES_ROOT}/var/mongo"
  mkdir -p "${MILLEGRILLES_ROOT}/var/nginx/html"
  mkdir -p "${MILLEGRILLES_ROOT}/var/files"
  mkdir -p "${MILLEGRILLES_ROOT}/var/backup/domains"

  echo "[OK] Repertoires crees"
}

copier_fichiers() {
  echo "[INFO] Copier fichiers systeme"
  cp -v "${REP_ETC}/idmg_validation.json" "${MILLEGRILLES_ROOT}/etc/"
  cp -vr "${REP_ETC}/compose" "${MILLEGRILLES_ROOT}/etc/"
  cp -iv "${REP_ETC}/nginx/config/"* "${MILLEGRILLES_ROOT}/etc/nginx"
  cp -vr "${REPO_ROOT}/bin" "${MILLEGRILLES_ROOT}/"

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

  echo "[INFO] Copying protege level nginx files"
  cp -iv "${REP_ETC}/nginx/nginx_protege/"* "${MILLEGRILLES_ROOT}/etc/nginx"

  echo "[INFO] Generating Root CA..."

  # Generate a random password for the root CA
  local password
  password=$(openssl rand -base64 32)
  ./bin/x509/ca_new.sh $password

  echo "[INFO] Generating Signing CA..."
  ./bin/x509/ca_signing.sh --password "$password"

  echo "[INFO] Generating Node Certificate..."
  "${PATH_VENV}/bin/python3" bin/x509/ca_protege.py \
    --millegrilles-root "${MILLEGRILLES_ROOT}" \
    --ca-pem "${MILLEGRILLES_ROOT}/secrets/certissuer/signing_ca.pem"

  # Get IDMG for configuration
  IDMG=$("${PATH_VENV}/bin/python3" bin/utils/get_idmg.py "${MILLEGRILLES_ROOT}/etc/millegrille.pem")

  if [ -z "$IDMG" ]; then
    echo "[ERROR] Failed to retrieve IDMG from Root CA."
    exit 1
  fi

  echo "IDMG=$IDMG" >> "${MILLEGRILLES_ROOT}/config.env"

  # Load configuration
  set -a
  . "${MILLEGRILLES_ROOT}/config.env"
  set +a

  echo "[INFO] Preparing node systemd configuration files for protege"
  ./bin/install/setup_systemd_protege.sh "${MILLEGRILLES_ROOT}/config.env"

  echo "[INFO] Download and start certissuer"
  systemctl --user daemon-reload
  docker compose -f "${MILLEGRILLES_ROOT}/etc/compose/coremodules/certissuer.yml" pull
  systemctl --user restart "${INSTANCE_NAME}-certissuer"
  sleep 5  # Wait for certissuer to start

  echo "[INFO] Generate all local certificates and passwords in secrets directory"
  export CA_PATH="${MILLEGRILLES_ROOT}/etc/millegrille.pem"
  export CERT_PATH="${MILLEGRILLES_ROOT}/secrets/manager.pem"
  export KEY_PATH="${MILLEGRILLES_ROOT}/secrets/manager.pem"
  # ,Run manager to generate certificates/passwords
  "${PATH_VENV}/bin/python3" -m millegrilles_instance --config "${MILLEGRILLES_ROOT}" --init

  # Note : the download can take a while so this makes sure we don't starts services that are not already on disk
  echo "[INFO] Download all the required images"
  docker compose -f "${MILLEGRILLES_ROOT}/etc/compose/include/protege_service_deps.yml" pull
  docker compose -f "${MILLEGRILLES_ROOT}/etc/compose/middleware/node-protege.yml" pull

  echo "[INFO] Start middleware"
  systemctl --user restart "${INSTANCE_NAME}-nginx"
  sleep 5
  systemctl --user restart "${INSTANCE_NAME}-middleware"
  sleep 10
  systemctl --user restart "${INSTANCE_NAME}-core"
  systemctl --user restart "${INSTANCE_NAME}-maitredescles"

  echo "[INFO] Start services and node manager "
  systemctl --user restart "${INSTANCE_NAME}-manager"

  # Enable services on start, register timers
  systemctl --user enable "${INSTANCE_NAME}-nginx"
  systemctl --user enable "${INSTANCE_NAME}-middleware"
  systemctl --user enable "${INSTANCE_NAME}-core"
  systemctl --user enable "${INSTANCE_NAME}-maitredescles"
  systemctl --user enable "${INSTANCE_NAME}-manager"

  # Activate the certificate updater with timer
  systemctl --user enable --now "${INSTANCE_NAME}-certs_updater.timer"
  systemctl --user enable --now "${INSTANCE_NAME}-certs_updater.service"
  systemctl --user start "${INSTANCE_NAME}-certs_updater"
  echo "[OK] Services and node manager started"

  echo "[INFO] Installing web applications from catalogue"
  "${MILLEGRILLES_ROOT}/bin/install/manage_apps.py" install \
    --name authentication \
    --catalogue_url "${REPO_ROOT}/etc/catalogue/applicationCatalogue.json" \
    --root "${MILLEGRILLES_ROOT}"
  "${MILLEGRILLES_ROOT}/bin/install/manage_apps.py" install \
    --name coupdoeil \
    --catalogue_url "${REPO_ROOT}/etc/catalogue/applicationCatalogue.json" \
    --root "${MILLEGRILLES_ROOT}"

  echo "[OK] Protege installation complete, IDMG=${IDMG}."
  echo
  echo "------------------------------------------------------------------------------"
  echo "# Certificate Authority (CA) PEM File"
  echo "# ${MILLEGRILLES_ROOT}/secrets/certissuer/ca.pem"
  cat "${MILLEGRILLES_ROOT}/secrets/certissuer/ca.pem"
  echo "------------------------------------------------------------------------------"
  echo "CA Password: $password"
  echo "------------------------------------------------------------------------------"
  echo
  echo "IMPORTANT: Save the password (above) and ca.pem file content! The password is not saved anywhere."
  echo "!! The PASSWORD is ONLY shown here !!"
  echo "Both the password and CA file are required for future operations (restoring backups, system updates, deploying secure nodes, etc)."
  echo "To increase security, store the ca.pem file and the password separately."
  echo
  echo "[INFO] Server url: https://${INSTANCE_DOMAIN}."
  echo "[INFO] https://localhost will also work properly on this machine"
  echo "[INFO] If you don't plan to use a web certificate authority like Let's Encrypt,"
  echo "       import the following file as a new website CA certificate in your browser:"
  echo "       ${MILLEGRILLES_ROOT}/secrets/webcass.cert.pem"
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
