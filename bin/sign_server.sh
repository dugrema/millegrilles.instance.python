#!/bin/bash
set -e

# Function to print error and exit
error_exit() {
    echo "Error: $1" >&2
    exit 1
}

# Check if arguments are provided
if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <hostname> [additional_hostnames...]"
    exit 1
fi

# Check if openssl is installed
if ! command -v openssl &> /dev/null; then
    error_exit "openssl is not installed. Please install it and try again."
fi

# Configuration
CA_DIR=".certs"
CA_CERT="$CA_DIR/pki.webcass.cert"
CA_KEY="$CA_DIR/pki.webcass.key"

# Check if CA exists
if [ ! -f "$CA_CERT" ] || [ ! -f "$CA_KEY" ]; then
    error_exit "CA certificates not found in $CA_DIR. Please run ./bin/generate_selfsigned.sh first."
fi

# Arguments
PRIMARY_HOSTNAME="$1"
shift
ADDITIONAL_HOSTNAMES=("$@")

# Output files
OUTPUT_CERT="${PRIMARY_HOSTNAME}.cert"
OUTPUT_KEY="${PRIMARY_HOSTNAME}.key"

echo "Generating certificate for: $PRIMARY_HOSTNAME"

# Create a temporary config for SAN
CONF_FILE=$(mktemp) || error_exit "Failed to create temporary config file"
CSR_FILE=$(mktemp) || error_exit "Failed to create temporary CSR file"
SERVER_CERT_TEMP=$(mktemp) || error_exit "Failed to create temporary server cert file"

# Cleanup on exit
trap 'rm -f "$CONF_FILE" "$CSR_FILE" "$SERVER_CERT_TEMP"' EXIT

# Build the config file
cat <<EOF > "$CONF_FILE"
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = $PRIMARY_HOSTNAME

[v3_req]
keyUsage = keyEncipherment, dataEncipherment, digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
EOF

# Function to determine if a string is an IP address
is_ip() {
    local ip=$1
    if [[ $ip =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        return 0
    else
        return 1
    fi
}

# Add the primary and additional hostnames to the SAN section
COUNTER=2
# We treat the primary hostname as part of the SAN list too.
# The user might provide IP addresses or hostnames.
for host in "$PRIMARY_HOSTNAME" "${ADDITIONAL_HOSTNAMES[@]}"; do
    if is_ip "$host"; then
        echo "IP.$COUNTER = $host" >> "$CONF_FILE"
    else
        echo "DNS.$COUNTER = $host" >> "$CONF_FILE"
    fi
    COUNTER=$((COUNTER + 1))
done

# Generate Server Key and CSR
openssl genrsa -out "$OUTPUT_KEY" 2048 &> /dev/null || error_exit "Failed to generate server key"
openssl req -new -key "$OUTPUT_KEY" -out "$CSR_FILE" -config "$CONF_FILE" &> /dev/null || error_exit "Failed to generate CSR"

# Sign Server Certificate with Root CA
openssl x509 -req -in "$CSR_FILE" -CA "$CA_CERT" -CAkey "$CA_KEY" \
    -CAcreateserial -out "$SERVER_CERT_TEMP" -days 825 -sha256 -extensions v3_req -extfile "$CONF_FILE" &> /dev/null || error_exit "Failed to sign server certificate"

# Create certificate chain: server.cert then CA.cert
cat "$SERVER_CERT_TEMP" "$CA_CERT" > "$OUTPUT_CERT"

echo "Success!"
echo "Certificates generated:"
echo "  $OUTPUT_CERT (Chain: server + CA)"
echo "  $OUTPUT_KEY"
