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
FICHE_URL=""
EXISTING_CA_CERT=""

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
  echo "  --fiche <url>      URL of the fiche file (required for non-protege types)"
  echo "  --ca <path>        Path to an existing Root CA certificate"
  echo "  --help             Display this help message"
  exit 0
}

while [[ "$#" -gt 0 ]]; do
  case $1 in
    --prefix) MILLEGRILLES_ROOT="$2"; shift ;;
    --name) INSTANCE_NAME="$2"; shift ;;
    --domain) INSTANCE_DOMAIN="$2"; shift ;;
    --type) TYPE="$2"; shift ;;
    --fiche) FICHE_URL="$2"; shift ;;
    --ca) EXISTING_CA_CERT="$2"; shift ;;
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
#  if [ "$TYPE" != "protege" ]; then
#    if [ -f "${MILLEGRILLES_ROOT}/etc/fiche_env" ]; then
#      source "${MILLEGRILLES_ROOT}/etc/fiche_env"
#      CERTISSUER_URL="https://${MQ_HOSTNAME}:${MTLS_PORT}"
#    else
#      echo "[ERROR] fiche_env not found. Did you run process_fiche_file?"
#      exit 1
#    fi
#  else
#    CERTISSUER_URL="http://localhost:2080"
#  fi

  # Change in design - certissuer is always local (3.protege and 4.secure)
  # Otherwise the manager MUST connect to MQ to renew certificates
  # If manager cert is expired, it must be renewed manually using CSR signing scripts
  if [ "$TYPE" == "protege" ] || [ "$TYPE" == "secure" ]; then
    CERTISSUER_URL="http://localhost:2080"
  else
    # Not available for other types
    CERTISSUER_URL=""
  fi

  {
    echo "INSTANCE_ID=\"${INSTANCE_ID}\""
    echo "CONTAINER_UID=\"${CONTAINER_UID}\""
    echo "CONTAINER_GID=\"${CONTAINER_GID}\""
    echo "MILLEGRILLES_ROOT=\"${MILLEGRILLES_ROOT}\""
    echo "MOUNT_FILEHOST=\"${MILLEGRILLES_ROOT}/var/filehost\""
    echo "MOUNT_MONGO=\"${MILLEGRILLES_ROOT}/var/mongo\""
    echo "INSTANCE_NAME=\"${INSTANCE_NAME}\""
    echo "INSTANCE_DOMAIN=\"${INSTANCE_DOMAIN}\""
    echo "MANAGER_URL=\"https://localhost:2443\""
    echo "CERTISSUER_URL=\"${CERTISSUER_URL}\""
    echo "REDIS_URL=\"rediss://localhost:6379\""
    echo "SECURITE=\"${SECURITE}\""
    if [ "$TYPE" != "protege" ]; then
      echo "MQ_HOSTNAME=${MQ_HOSTNAME}"
      echo "MQ_PORT=${MQ_PORT}"
      echo "MTLS_PORT=${MTLS_PORT}"
      echo "IDMG=${IDMG}"
    fi
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
  mkdir -p "${MILLEGRILLES_ROOT}/etc/compose/applications"

  if [ "$TYPE" != "secure" ]; then
    mkdir -p "${MILLEGRILLES_ROOT}/var/mq"
  fi

  if [ "$TYPE" == "secure" ] || [ "$TYPE" == "protege" ]; then
    mkdir -p "${MILLEGRILLES_ROOT}/secrets/certissuer"
    mkdir -p "${MILLEGRILLES_ROOT}/var/mongo"
    mkdir -p "${MILLEGRILLES_ROOT}/var/backup/domains"
    mkdir -p "${MILLEGRILLES_ROOT}/var/backup/mongo"
  fi

  # Type 4.secure does not have nginx (or any ports exposed)
  if [ "$TYPE" != "secure" ]; then
    mkdir -p "${MILLEGRILLES_ROOT}/etc/nginx/applications"
    mkdir -p "${MILLEGRILLES_ROOT}/var/nginx/html"
  fi

  echo "[OK] Repertoires crees"
}

copier_fichiers() {
  echo "[INFO] Copier fichiers systeme"
  cp -vr "${REP_ETC}/compose" "${MILLEGRILLES_ROOT}/etc/"
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

#configurer_docker_network() {
#  echo "[INFO] Configurer docker pour instance: ${INSTANCE_NAME}"
#  docker network create --ipv6 --subnet "2001:db8:3::/64" --attachable "${INSTANCE_NAME}_net" > /dev/null 2>&1 || true
#  echo "[OK] Configuration docker network completee"
#}

configurer_docker_network() {
  echo "[INFO] Configurer docker pour instance: ${INSTANCE_NAME}"

  local SUBNET=""
  local EXISTING_SUBNETS
  EXISTING_SUBNETS=$(docker network inspect $(docker network ls -q) --format '{{range .IPAM.Config}}{{.Subnet}}{{"\n"}}{{end}}' 2>/dev/null)

  # Try to find an unused IPv6 subnet
  for i in $(seq 1 255); do
    local HEX_I
    HEX_I=$(printf '%x' "$i")
    local CANDIDATE="2001:db8:${HEX_I}::/64"

    if ! echo "$EXISTING_SUBNETS" | grep -Fxq "$CANDIDATE"; then
      SUBNET="$CANDIDATE"
      break
    fi
  done

  if [ -z "$SUBNET" ]; then
    echo "[ERROR] Could not find an unused IPv6 subnet in the range 2001:db8:1::/64 to 2001:db8:ff::/64"
    exit 1
  fi

  echo "[INFO] Using subnet $SUBNET"
  docker network create --ipv6 --subnet "$SUBNET" --attachable "${INSTANCE_NAME}_net" > /dev/null 2>&1 || true
  echo "[OK] Configuration docker network completee"
}

process_fiche_file() {
  if [ "$TYPE" == "protege" ]; then
    return 0
  fi

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

install_instance_v2() {
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
    if [ "$TYPE" != "secure" ]; then
      install_web_files
    fi
    configurer_docker_network
  else
    echo "[WARN] Dossier configuration déjà existant. Installation ignorée."
  fi
}

generate_signing_ca() {
    echo "[INFO] Generating Signing CSR from existing CA..."
    mkdir -p "${MILLEGRILLES_ROOT}/secrets/certissuer"

    # Generate an unencrypted ed25519 private key for the signing CA
    openssl genpkey -algorithm ed25519 -out "${MILLEGRILLES_ROOT}/secrets/certissuer/signing_ca_key.pem"

    # Generate the Signing CA CSR
    . "${PATH_VENV}/bin/activate"
    IDMG=$(python3 bin/utils/get_idmg.py "${MILLEGRILLES_ROOT}/etc/millegrille.pem")
    if [ -z "$IDMG" ]; then
      echo "[ERROR] Failed to retrieve IDMG from existing Root CA."
      exit 1
    fi

    openssl req -new -key "${MILLEGRILLES_ROOT}/secrets/certissuer/signing_ca_key.pem" \
      -out "${MILLEGRILLES_ROOT}/secrets/certissuer/ca.csr" \
      -subj "/CN=${INSTANCE_ID}/OU=${INSTANCE_NAME}/O=${IDMG}"

    # Wait for user to paste the certificate
    echo "[INFO] Use the following certificate request"
    echo "[INFO] ---------------------------------------------------"
    cat "${MILLEGRILLES_ROOT}/secrets/certissuer/ca.csr"
    echo "[INFO] ---------------------------------------------------"
    echo "[INFO] Please paste the signed certificate for the Signing CA below and press Ctrl+D:"
    cat > "${MILLEGRILLES_ROOT}/secrets/certissuer/signing_ca_cert.pem"

    if [ ! -s "${MILLEGRILLES_ROOT}/secrets/certissuer/signing_ca_cert.pem" ]; then
      echo "[ERROR] Certificate input was empty."
      exit 1
    fi

    # Combine key and certificate into signing_ca.pem
    cat "${MILLEGRILLES_ROOT}/secrets/certissuer/signing_ca_key.pem" "${MILLEGRILLES_ROOT}/secrets/certissuer/signing_ca_cert.pem" > "${MILLEGRILLES_ROOT}/secrets/certissuer/signing_ca.pem"

    # Clean up temporary files
    rm "${MILLEGRILLES_ROOT}/secrets/certissuer/ca.csr" "${MILLEGRILLES_ROOT}/secrets/certissuer/signing_ca_key.pem" "${MILLEGRILLES_ROOT}/secrets/certissuer/signing_ca_cert.pem"

    echo "[INFO] Signing CA assembled from user input."
}

install_protege_instance() {
  echo "[INFO] Starting Protege installation..."
  
  install_instance_v2
  source "${MILLEGRILLES_ROOT}/config.env"

  echo "[INFO] Copying protege level nginx files"
  cp -iv "${REP_ETC}/nginx/nginx_protege/"* "${MILLEGRILLES_ROOT}/etc/nginx"

  local password=""
  if [ -n "$EXISTING_CA_CERT" ]; then
    if [ ! -f "$EXISTING_CA_CERT" ]; then
      echo "[ERROR] Existing CA certificate not found at $EXISTING_CA_CERT"
      exit 1
    fi
    echo "[INFO] Using existing Root CA from $EXISTING_CA_CERT"
    cp "$EXISTING_CA_CERT" "${MILLEGRILLES_ROOT}/etc/millegrille.pem"

    generate_signing_ca
    password="N/A (Using unencrypted signing key)"
  else
    echo "[INFO] Generating Root CA..."
    # Generate a random password for the root CA
    password=$(openssl rand -base64 32)
    ./bin/x509/ca_new.sh $password

    echo "[INFO] Generating Signing CA..."
    ./bin/x509/ca_signing.sh --password "$password" --instanceid "$INSTANCE_ID"
  fi

  echo "[INFO] Generating Node Certificate..."
  "${PATH_VENV}/bin/python3" bin/x509/sign_protege.py \
    --millegrilles-root "${MILLEGRILLES_ROOT}" \
    --ca-pem "${MILLEGRILLES_ROOT}/secrets/certissuer/signing_ca.pem" \
    --instance-id $INSTANCE_ID

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

  # Initialize the local filehost repository
  mkdir -p "${MILLEGRILLES_ROOT}/var/filehost/files/${IDMG}"

  echo "[INFO] Preparing node systemd configuration files for protege"
  ./bin/install/setup_systemd_protege.sh "${MILLEGRILLES_ROOT}/config.env"

  echo "[INFO] Download and start certissuer"
  systemctl --user daemon-reload
  docker compose -f "${MILLEGRILLES_ROOT}/etc/compose/coremodules/certissuer.yml" pull
  systemctl --user enable --now "${INSTANCE_NAME}-certissuer"
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

  echo "[INFO] Start nginx"
  systemctl --user restart "${INSTANCE_NAME}-nginx"
  sleep 5
  echo "[INFO] Start middleware"
  systemctl --user restart "${INSTANCE_NAME}-middleware"
  sleep 10

  echo "[INFO] Installing applications from catalogue"
  "${MILLEGRILLES_ROOT}/bin/manage_apps.py" install --name core --noreload
  "${MILLEGRILLES_ROOT}/bin/manage_apps.py" install --name maitredescles --noreload
  "${MILLEGRILLES_ROOT}/bin/manage_apps.py" install --name webapiprotege --noreload
  "${MILLEGRILLES_ROOT}/bin/manage_apps.py" install --name coupdoeil2 --noreload
  docker compose -f "${MILLEGRILLES_ROOT}/etc/compose/applications.yml" pull

  echo "[INFO] Start services and node manager "
  systemctl --user reload "${INSTANCE_NAME}-nginx"

  # Enable services on start
  systemctl --user enable "${INSTANCE_NAME}-nginx"
  systemctl --user enable --now "${INSTANCE_NAME}-middleware"
  systemctl --user enable --now  "${INSTANCE_NAME}-applications"
  systemctl --user enable --now "${INSTANCE_NAME}-manager"

  # Activate the certificate updater with timer
  systemctl --user enable --now "${INSTANCE_NAME}-certs_updater.timer"
  systemctl --user enable --now "${INSTANCE_NAME}-certs_updater.service"
  systemctl --user enable --now "${INSTANCE_NAME}-backup.timer"
  systemctl --user enable --now "${INSTANCE_NAME}-backup.service"
  echo "[OK] Services and node manager started"

  echo "[OK] Protege installation complete, IDMG=${IDMG}."
  echo
  if [ -f "${MILLEGRILLES_ROOT}/secrets/certissuer/ca.pem" ]; then
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
  fi
  echo
  echo "[INFO] Server url: https://${INSTANCE_DOMAIN}."
  echo "[INFO] https://localhost will also work properly on this machine"
  echo "[INFO] If you don't plan to use a web certificate authority like Let's Encrypt,"
  echo "       import the following file as a new website CA certificate in your browser:"
  echo "       ${MILLEGRILLES_ROOT}/secrets/webcass.cert.pem"
}

install_secure_instance() {
  echo "[INFO] Starting Secure installation..."
  
  install_instance_v2
  source "${MILLEGRILLES_ROOT}/config.env"

  generate_signing_ca

  echo "[INFO] Generating Node Manager Certificate..."
  "${PATH_VENV}/bin/python3" bin/x509/sign_protege.py \
    --millegrilles-root "${MILLEGRILLES_ROOT}" \
    --ca-pem "${MILLEGRILLES_ROOT}/secrets/certissuer/signing_ca.pem" \
    --instance-id $INSTANCE_ID

  echo "[INFO] Preparing node systemd configuration files for secure"
  ./bin/install/setup_systemd_secure.sh "${MILLEGRILLES_ROOT}/config.env"

  echo "[INFO] Download and start certissuer"
  systemctl --user daemon-reload
  docker compose -f "${MILLEGRILLES_ROOT}/etc/compose/coremodules/certissuer.yml" pull
  systemctl --user restart "${INSTANCE_NAME}-certissuer"
  sleep 5

  echo "[INFO] Initialize manager certificates"
  "${PATH_VENV}/bin/python3" -m millegrilles_instance --config "${MILLEGRILLES_ROOT}" --init

  echo "[INFO] Download and start middleware"
  docker compose -f "${MILLEGRILLES_ROOT}/etc/compose/middleware/node-secure.yml" pull
  systemctl --user restart "${INSTANCE_NAME}-middleware"

  echo "[INFO] Start manager"
  systemctl --user restart "${INSTANCE_NAME}-manager"

  echo "[OK] Secure installation complete."
}

install_prive_instance() {
  echo "[INFO] Starting Private installation..."

  install_instance_v2
  source "${MILLEGRILLES_ROOT}/config.env"

  echo "[INFO] Copying protege level nginx files"
  cp -iv "${REP_ETC}/nginx/nginx_prive/"* "${MILLEGRILLES_ROOT}/etc/nginx"

  echo "[INFO] Requesting Node Manager Certificate..."
  "${PATH_VENV}/bin/python3" bin/x509/request_satellite.py

  # Initialize the local filehost repository
  mkdir -p "${MILLEGRILLES_ROOT}/var/filehost/files/${IDMG}"

  echo "[INFO] Preparing node systemd configuration files for secure"
  ./bin/install/setup_systemd_prive.sh "${MILLEGRILLES_ROOT}/config.env"

  echo "[INFO] Download and start middleware"

  # Note : the download can take a while so this makes sure we don't starts services that are not already on disk
  echo "[INFO] Download all the required images"
  docker compose -f "${MILLEGRILLES_ROOT}/etc/compose/include/private_service_deps.yml" pull
  docker compose -f "${MILLEGRILLES_ROOT}/etc/compose/middleware/node-prive.yml" pull
  systemctl --user restart "${INSTANCE_NAME}-middleware"

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
    protege)
      install_protege_instance
      ;;
    secure)
      install_secure_instance
      ;;
    prive)
      install_prive_instance
      ;;
    public)
      echo "[ERROR] Not implemented yet: $TYPE"
      exit 1
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
