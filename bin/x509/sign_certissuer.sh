#!/bin/env bash
set -euo pipefail

# Usage: ./sign_certissuer.sh <ca.pem>

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <ca.pem>" >&2
  exit 1
fi

CA_PEM="$1"
if [ ! -f "$CA_PEM" ]; then
  echo "[ERROR] CA file not found: $CA_PEM" >&2
  exit 1
fi

# 1. Get CA password
# We use -s to hide the password input
read -s -p "Enter CA password: " CA_PASSWORD
echo "" >&2

# 2. Get CSR from stdin
echo "[INFO] Paste the CSR below and press Ctrl+D to continue:" >&2
CSR_FILE=$(mktemp)
trap 'rm -f "$CSR_FILE"' EXIT
cat > "$CSR_FILE"

if [ ! -s "$CSR_FILE" ]; then
  echo "[ERROR] CSR was empty." >&2
  exit 1
fi

# 3. Create a temporary config for extensions
# Using the same extensions as ca_signing.sh
TMP_CONF=$(mktemp)
trap 'rm -f "$CSR_FILE" "$TMP_CONF"' EXIT
cat <<EOF > "$TMP_CONF"
[v3_signing_ca]
keyUsage = Certificate Sign, CRL Sign
basicConstraints = critical, CA:TRUE, pathlen:0
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
EOF

# 4. Sign the CSR
# We use the same CA file for both -CA and -CAkey as it contains both key and cert
CERT_FILE=$(mktemp)
openssl x509 -req \
  -CA "$CA_PEM" \
  -CAkey "$CA_PEM" \
  -CAcreateserial \
  -passin "pass:$CA_PASSWORD" \
  -in "$CSR_FILE" \
  -out "$CERT_FILE" \
  -days 547 \
  -extfile "$TMP_CONF" \
  -extensions v3_signing_ca

# 5. Output the certificate to stdout
cat "$CERT_FILE"
