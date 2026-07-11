#!/bin/env bash
set -ex
set -euo pipefail

# Ensure MILLEGRILLES_ROOT is set
if [ -z "${MILLEGRILLES_ROOT:-}" ]; then
  echo "[ERROR] MILLEGRILLES_ROOT is not set. Please source your environment or set it explicitly."
  exit 1
fi

# Ensure INSTANCE_NAME is set
if [ -z "${INSTANCE_NAME:-}" ]; then
  echo "[ERROR] INSTANCE_NAME is not set."
  exit 1
fi

usage() {
  echo "Usage: $0 --password <password>"
  exit 1
}

# Parse arguments
PASSWORD=""
while [[ "$#" -gt 0 ]]; do
  case $1 in
    --password) PASSWORD="$2"; shift ;;
    *) usage ;;
  esac
  shift
done

# Get INSTANCE_ID or default
INSTANCE_ID="${INSTANCE_ID:-$(uuidgen 2>/dev/null || echo "default-id")}"

# Define paths
SIGNING_CA_DIR="${MILLEGRILLES_ROOT}/etc/secrets/certissuer"
ROOT_CA="${SIGNING_CA_DIR}/ca.pem"
SIGNING_CA_CERT="${SIGNING_CA_DIR}/cert.pem"
SIGNING_CA_KEY="${SIGNING_CA_DIR}/key.pem"

# Check if Root CA exists
if [ ! -f "$ROOT_CA" ]; then
  echo "[ERROR] Root CA not found at $MILLEGRILLES_ROOT/etc/secrets/certissuer/"
  echo "[INFO] Please run bin/ca_new.sh first."
  exit 1
fi

# Get IDMG from the Root CA certificate
#export PYTHONPATH="${PYTHONPATH}:/home/vaicoder1/work/millegrilles.messages.python:$(pwd)"
# Activate python venv
. "${MILLEGRILLES_ROOT}/venv/bin/activate"
IDMG=$(python3 bin/get_idmg.py "$ROOT_CA")

if [ -z "$IDMG" ]; then
  echo "[ERROR] Failed to retrieve IDMG from Root CA."
  exit 1
fi

echo "[INFO] Retrieved IDMG: $IDMG"

# Create required directories
mkdir -p "$SIGNING_CA_DIR"

# Temporary files
TMP_CONF=$(mktemp)
trap 'rm -f "$TMP_CONF"' EXIT

# Create OpenSSL configuration for extensions
cat <<EOF > "$TMP_CONF"
[v3_signing_ca]
keyUsage = Certificate Sign, CRL Sign
basicConstraints = critical, CA:TRUE, pathlen:0
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
EOF

# 1. Generate the unencrypted signing CA private key
openssl genpkey -algorithm ed25519 -out "$SIGNING_CA_KEY"

# 2. Generate the CSR
openssl req -new -key "$SIGNING_CA_KEY" \
  -out "${SIGNING_CA_DIR}/ca.csr" \
  -subj "/CN=${INSTANCE_ID}/OU=${INSTANCE_NAME}/O=${IDMG}"

# 3. Sign the CSR with the Root CA
# 18 months = 547 days
# PASSWORD_PARAMS="-passin pass"
if [ -z "$PASSWORD" ]; then
  PASSWORD_PARAMS=""  # Omit param, openssl will prompt user
else
  PASSWORD_PARAMS="-passin pass:$PASSWORD"
fi

openssl x509 -req \
  -CA "$ROOT_CA" \
  -CAkey "$ROOT_CA" \
  -CAcreateserial \
  $PASSWORD_PARAMS \
  -in "${SIGNING_CA_DIR}/ca.csr" \
  -out "$SIGNING_CA_CERT" \
  -days 547 \
  -extfile "$TMP_CONF" \
  -extensions v3_signing_ca

# 4. Combine key and cert into signing_ca.pem
cat "$SIGNING_CA_KEY" "$SIGNING_CA_CERT" > "${SIGNING_CA_DIR}/signing_ca.pem"

# Cleanup CSR, serial file and separate key/cert
rm "${SIGNING_CA_DIR}/ca.csr"
rm "${SIGNING_CA_DIR}/ca.srl" 2>/dev/null || true
rm "$SIGNING_CA_CERT" "$SIGNING_CA_KEY"

echo "[INFO] Signing CA generated successfully."
