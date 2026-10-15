#!/bin/env bash
# Creates a new MilleGrille certificate (CA)

set -euo pipefail

# Ensure MILLEGRILLES_ROOT is set
if [ -z "${MILLEGRILLES_ROOT:-}" ]; then
  echo "[ERROR] MILLEGRILLES_ROOT is not set. Please source your environment or set it explicitly."
  exit 1
fi

# Get INSTANCE_NAME or default
INSTANCE_NAME="${INSTANCE_NAME:-millegrille}"
CERTISSUER_PATH="${MILLEGRILLES_ROOT}/secrets/certissuer"

# Create required directories
mkdir -p "${CERTISSUER_PATH}/tmp"

# Generate a random password for the root CA
# PASSWORD=$(openssl rand -base64 32)
if [ -z "$1" ]; then
  # Generate a random password for the root CA
  PASSWORD=$(openssl rand -base64 32)
else
  PASSWORD="$1"
fi

echo "Using CA password '$PASSWORD'"

# Temporary files
TMP_CONF=$(mktemp)
trap 'rm -f "$TMP_CONF"' EXIT

# Create OpenSSL configuration for extensions
cat <<EOF > "$TMP_CONF"
[v3_ca]
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, keyCertSign
basicConstraints = critical, CA:TRUE
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
EOF

# 1. Generate the encrypted ed25519 private key
openssl genpkey -algorithm ed25519 -aes256 -out "${CERTISSUER_PATH}/tmp/ca_key.pem" -pass "pass:$PASSWORD"

# 2. Generate the self-signed certificate
# We use a CSR then sign it with x509 to ensure extensions are handled correctly
openssl req -new -key "${CERTISSUER_PATH}/tmp/ca_key.pem" \
  -passin "pass:$PASSWORD" \
  -out "${CERTISSUER_PATH}/tmp/ca.csr" \
  -subj "/CN=${INSTANCE_NAME}/O=MilleGrillles"

openssl x509 -req \
  -in "${CERTISSUER_PATH}/tmp/ca.csr" \
  -signkey "${CERTISSUER_PATH}/tmp/ca_key.pem" \
  -passin "pass:$PASSWORD" \
  -out "${CERTISSUER_PATH}/tmp/ca.pem" \
  -days 7300 \
  -extfile "$TMP_CONF" \
  -extensions v3_ca

# Clean up CSR
rm "${CERTISSUER_PATH}/tmp/ca.csr"

# 3. Copy the certificate to the requested location
cp "${CERTISSUER_PATH}/tmp/ca.pem" "${MILLEGRILLES_ROOT}/etc/millegrille.pem"

# 4. Get the IDMG hash value
. "${MILLEGRILLES_ROOT}/venv/bin/activate"
IDMG=$(python3 bin/utils/get_idmg.py "${CERTISSUER_PATH}/tmp/ca.pem")

# 5. Move the old tmp/ folder to the certissuer domain (by IDMG)
CERTDOMAIN_PATH="${CERTISSUER_PATH}/${IDMG}"
mv "${CERTISSUER_PATH}/tmp" "$CERTDOMAIN_PATH"

# Combine encrypted key and cert into single file
echo "# MilleGrilles self-signed CA key" > "${CERTDOMAIN_PATH}/cakey.pem"
echo "# Instance: $INSTANCE_NAME" >> "${CERTDOMAIN_PATH}/cakey.pem"
echo "# IDMG: $IDMG" >> "${CERTDOMAIN_PATH}/cakey.pem"
cat "${CERTDOMAIN_PATH}/ca_key.pem" \
    "${CERTDOMAIN_PATH}/ca.pem" >> "${CERTDOMAIN_PATH}/cakey.pem"

# Remove old key file, keep ca.pem and cakey.pem
rm "${CERTDOMAIN_PATH}/ca_key.pem"

echo "[INFO] Root CA generated successfully."
echo
echo "------------------------------------------------------------------------------"
echo "Root CA Password for $INSTANCE_NAME: $PASSWORD"
echo "------------------------------------------------------------------------------"
echo
echo "[WARN] You *MUST* save this password (e.g. in a password manager), this is the only time it will be shown."
echo "[INFO] You can test it by running: openssl pkey -noout -text -in ${CERTDOMAIN_PATH}/ca.pem"

