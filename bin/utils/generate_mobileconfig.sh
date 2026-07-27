#!/bin/bash
set -e

# Function to print error and exit
error_exit() {
    echo "Error: $1" >&2
    exit 1
}

# Check if uuidgen is installed
if ! command -v uuidgen &> /dev/null; then
    error_exit "uuidgen is not installed. Please install it to generate the configuration profile."
fi

# Check if openssl is installed
if ! command -v openssl &> /dev/null; then
    error_exit "openssl is not installed."
fi

# Configuration
CA_DIR=".certs"
CA_CERT="$CA_DIR/pki.webcass.cert"
OUTPUT_FILE="pki.webcass.mobileconfig"

# Check if CA certificate exists
if [ ! -f "$CA_CERT" ]; then
    error_exit "CA certificate not found at $CA_CERT. Please run ./bin/generate_selfsigned.sh first."
fi

echo "Generating iOS Configuration Profile: $OUTPUT_FILE"

# Generate UUIDs
PROFILE_UUID=$(uuidgen)
PAYLOAD_UUID=$(uuidgen)

# Base64 encode the certificate (single line, no newlines)
# On Linux, base64 -w 0 is used. On macOS, base64 -b 0 doesn't exist, so we use a fallback.
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    CERT_BASE64=$(base64 -w 0 < "$CA_CERT")
else
    CERT_BASE64=$(base64 < "$CA_CERT")
fi

# Create the .mobileconfig file
cat <<EOF > "$OUTPUT_FILE"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadContent</key>
    <array>
        <dict>
            <key>Certificate</key>
            <string>$CERT_BASE64</string>
            <key>PayloadDescription</key>
            <string>Adds a Root CA certificate for local development.</string>
            <key>PayloadDisplayName</key>
            <string>Local Dev CA Certificate</string>
            <key>PayloadIdentifier</key>
            <string>com.localdev.ca.$PAYLOAD_UUID</string>
            <key>PayloadType</key>
            <string>com.apple.security.root</string>
            <key>PayloadUUID</key>
            <string>$PAYLOAD_UUID</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
        </dict>
    </array>
    <key>PayloadDisplayName</key>
    <string>Local Development Root CA</string>
    <key>PayloadIdentifier</key>
    <string>com.localdev.profile.$PROFILE_UUID</string>
    <key>PayloadOrganization</key>
    <string>Local Development</string>
    <key>PayloadRemoval</key>
    <string>false</string>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadUUID</key>
    <string>$PROFILE_UUID</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
</dict>
</plist>
EOF

echo "Success! Profile created: $OUTPUT_FILE"
echo "Instructions for iOS:"
echo "1. Transfer $OUTPUT_FILE to your iPhone/iPad."
echo "2. Open the file on your device."
echo "3. Go to Settings > General > VPN & Device Management and install the profile."
echo "4. IMPORTANT: Go to Settings > General > About > Certificate Trust Settings and enable full trust for this CA."
