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

# Target directory for generated key/csr
CERT_DIR="${1:-.certs}"
mkdir -p "$CERT_DIR" || error_exit "Failed to create directory $CERT_DIR"

# Target directory for waiting cert
SECRETS_DIR="secrets"

# Get hostnames
HOSTNAME=$(hostname)
FQDN=$(hostname -f 2>/dev/null || echo "$HOSTNAME")

SERVER_KEY="$CERT_DIR/web.key.pem"
CSR_FILE="$CERT_DIR/web.csr"

echo "Generating server key: $SERVER_KEY"
openssl ecparam -name prime256v1 -genkey -noout -out "$SERVER_KEY" || error_exit "Failed to generate server key"

echo "Generating CSR: $CSR_FILE"
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

openssl req -new -key "$SERVER_KEY" -out "$CSR_FILE" -config "$CONF_FILE" &> /dev/null || error_exit "Failed to generate CSR"
rm "$CONF_FILE"

echo "CSR generated: $CSR_FILE"
echo "Server key generated: $SERVER_KEY"
echo "Waiting for signed certificate at $SECRETS_DIR/web.cert.pem ..."

# Wait for the certificate to appear in the secrets directory
while [ ! -f "$SECRETS_DIR/web.cert.pem" ]; do
    sleep 5
done

echo "Certificate detected at $SECRETS_DIR/web.cert.pem"

# Copy the key to secrets as well, so the application can use both.
if [ -f "$SERVER_KEY" ]; then
    echo "Copying server key to $SECRETS_DIR/web.key.pem"
    cp -v "$SERVER_KEY" "$SECRETS_DIR/web.key.pem"
fi

echo "Done! Certificate and key are now in $SECRETS_DIR/"
