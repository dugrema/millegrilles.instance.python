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

# Usage: ./web_sign_offline.sh <csr_file> <ca_cert> <ca_key> <output_cert> [ext_config_file]
if [ "$#" -lt 4 ]; then
    echo "Usage: $0 <csr_file> <ca_cert> <ca_key> <output_cert> [ext_config_file]"
    exit 1
fi

CSR_FILE=$1
CA_CERT=$2
CA_KEY=$3
OUTPUT_CERT=$4
EXT_CONFIG=$5

# Verify input files
[ -f "$CSR_FILE" ] || error_exit "CSR file not found: $CSR_FILE"
[ -f "$CA_CERT" ] || error_exit "CA certificate not found: $CA_CERT"
[ -f "$CA_KEY" ] || error_exit "CA key not found: $CA_KEY"

# If an extension config file is provided, use it.
if [ -n "$EXT_CONFIG" ] && [ -f "$EXT_CONFIG" ]; then
    echo "Using extensions from $EXT_CONFIG"
    openssl x509 -req -in "$CSR_FILE" -CA "$CA_CERT" -CAkey "$CA_KEY" \
        -CAcreateserial -out "$OUTPUT_CERT" -days 825 -sha256 -extfile "$EXT_CONFIG" || error_exit "Failed to sign certificate"
else
    echo "No extension config file provided. Signing without explicit extensions (SANs might be missing)."
    openssl x509 -req -in "$CSR_FILE" -CA "$CA_CERT" -CAkey "$CA_KEY" \
        -CAcreateserial -out "$OUTPUT_CERT" -days 825 -sha256 || error_exit "Failed to sign certificate"
fi

echo "Successfully signed certificate: $OUTPUT_CERT"
