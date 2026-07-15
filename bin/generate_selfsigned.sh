#!/bin/bash
set -e

# Function to print error and exit
error_exit() {
    echo "Error: $1" >&2
    exit 1
}

# Check if openssl is installed
if ! command -v openssl &> /dev/null; then
    error_exit "openssl is not installed. Please install it and try again."
fi

# Target directory for certs
CERT_DIR="${1:-.certs}"
mkdir -p "$CERT_DIR" || error_exit "Failed to create directory $CERT_DIR"

# Get hostnames
HOSTNAME=$(hostname)
FQDN=$(hostname -f 2>/dev/null || echo "$HOSTNAME")

echo "Generating certificates in $CERT_DIR"
echo "Hostnames included in SAN: localhost, 127.0.0.1, $HOSTNAME, $FQDN"

# Define file paths
ROOT_CA_KEY="$CERT_DIR/webcass.key.pem"
ROOT_CA_PEM="$CERT_DIR/webcass.cert.pem"
SERVER_KEY="$CERT_DIR/webss.key.pem"
SERVER_CRT="$CERT_DIR/webss.cert.1"
CHAIN_CRT="$CERT_DIR/webss.cert.pem"

# 1. Create Root CA
if [ ! -f "$ROOT_CA_PEM" ]; then
    echo "Creating Root CA..."
    openssl genrsa -out "$ROOT_CA_KEY" 2048 &> /dev/null || error_exit "Failed to generate Root CA key"
    openssl req -x509 -new -nodes -key "$ROOT_CA_KEY" -sha256 -days 3650 -out "$ROOT_CA_PEM" -subj "/CN=Local Dev CA" &> /dev/null || error_exit "Failed to generate Root CA certificate"
else
    echo "Root CA already exists. Skipping creation."
fi

# 2. Create Server Certificate
echo "Creating Server Certificate..."

# Create a temporary config for SAN
CONF_FILE=$(mktemp) || error_exit "Failed to create temporary config file"

cat <<EOF > "$CONF_FILE"
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = localhost

[v3_req]
keyUsage = keyEncipherment, dataEncipherment, digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = $HOSTNAME
DNS.3 = $FQDN
IP.1 = 127.0.0.1
EOF

# Generate Server Key and CSR
openssl genrsa -out "$SERVER_KEY" 2048 &> /dev/null || error_exit "Failed to generate server key"
openssl req -new -key "$SERVER_KEY" -out "$CERT_DIR/server.csr" -config "$CONF_FILE" &> /dev/null || error_exit "Failed to generate CSR"

# Sign Server Certificate with Root CA
openssl x509 -req -in "$CERT_DIR/server.csr" -CA "$ROOT_CA_PEM" -CAkey "$ROOT_CA_KEY" \
    -CAcreateserial -out "$SERVER_CRT" -days 825 -sha256 -extensions v3_req -extfile "$CONF_FILE" &> /dev/null || error_exit "Failed to sign server certificate"

cat $SERVER_CRT $ROOT_CA_PEM > $CHAIN_CRT

# Copy to web PEMs to get picked-up by nginx (if not already present)
cp -iv "$CHAIN_CRT" "$CERT_DIR/web.cert.pem"
cp -iv "$SERVER_KEY" "$CERT_DIR/web.key.pem"

# Cleanup
rm "$CERT_DIR/server.csr" "$CONF_FILE" "$SERVER_CRT" "$CERT_DIR/webcass.cert.srl"

echo "Success!"
echo "Certificates generated:"
echo "  $ROOT_CA_PEM (Install this in your browser/OS to trust the certs)"
echo "  $CHAIN_CRT"
echo "  $SERVER_KEY"
