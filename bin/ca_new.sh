#!/bin/env bash
set -euo pipefail

# Ensure MILLEGRILLES_ROOT is set
if [ -z "${MILLEGRILLES_ROOT:-}" ]; then
  echo "[ERROR] MILLEGRILLES_ROOT is not set. Please source your environment or set it explicitly."
  exit 1
fi

# Get INSTANCE_NAME or default
INSTANCE_NAME="${INSTANCE_NAME:-millegrille}"

# Create required directories
mkdir -p "${MILLEGRILLES_ROOT}/etc/secrets/certissuer"

# Generate a random password for the root CA
PASSWORD=$(openssl rand -base64 32)

# Temporary files
TMP_CONF=$(mktemp)
trap 'rm -f "$TMP_CONF"' EXIT

# Create OpenSSL configuration for extensions
cat <<EOF > "$TMP_CONF"
[v3_ca]
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, keyCertSign
basicConstraints = CA:TRUE
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
EOF

# 1. Generate the encrypted ed25519 private key
openssl genpkey -algorithm ed25519 -aes256 -out "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca_key.pem" -pass "pass:$PASSWORD"

# 2. Generate the self-signed certificate
# We use a CSR then sign it with x509 to ensure extensions are handled correctly
openssl req -new -key "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca_key.pem" \
  -passin "pass:$PASSWORD" \
  -out "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca.csr" \
  -subj "/CN=${INSTANCE_NAME}/O=MilleGrillles"

openssl x509 -req \
  -in "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca.csr" \
  -signkey "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca_key.pem" \
  -passin "pass:$PASSWORD" \
  -out "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca_cert.pem" \
  -days 7300 \
  -extfile "$TMP_CONF" \
  -extensions v3_ca

# Clean up CSR
rm "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca.csr"

# 3. Copy the certificate to the requested location
cp "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca_cert.pem" "${MILLEGRILLES_ROOT}/etc/millegrille.pem"

# 4. Get the IDMG hash value
. "${MILLEGRILLES_ROOT}/venv/bin/activate"
IDMG=$(python3 bin/get_idmg.py "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca_cert.pem")

# Combine encrypted key and cert into single file
echo "# MilleGrilles self-signed CA key" > "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca.pem"
echo "# Instance: $INSTANCE_NAME" >> "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca.pem"
echo "# IDMG: $IDMG" >> "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca.pem"
cat "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca_key.pem" \
    "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca_cert.pem" >> "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca.pem"

# Remove old separate files
rm "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca_cert.pem" \
   "${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca_key.pem"

echo "[INFO] Root CA generated successfully."
echo
echo "------------------------------------------------------------------------------"
echo "Root CA Password for $INSTANCE_NAME: $PASSWORD"
echo "------------------------------------------------------------------------------"
echo
echo "[WARN] You *MUST* save this password (e.g. in a password manager), this is the only time it will be shown."
echo "[INFO] You can test it by running: openssl pkey -noout -text -in ${MILLEGRILLES_ROOT}/etc/secrets/certissuer/ca.pem"

