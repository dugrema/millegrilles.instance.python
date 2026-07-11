#!/bin/bash

# Usage: ./setup_systemd_protege.sh <config_env_path>

set -e

CONFIG_FILE="$1"
TEMPLATE_DIR="etc/compose/systemd"
DEST_DIR="$HOME/.config/systemd/user"
NODE_TYPE="protege"

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <config_env_path>"
    exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file '$CONFIG_FILE' not found."
    exit 1
fi

# Extract values from config.env, removing quotes
MILLEGRILLES_ROOT=$(grep '^MILLEGRILLES_ROOT=' "$CONFIG_FILE" | cut -d'=' -f2 | sed 's/"//g')
INSTANCE_NAME=$(grep '^INSTANCE_NAME=' "$CONFIG_FILE" | cut -d'=' -f2 | sed 's/"//g')

if [ -z "$MILLEGRILLES_ROOT" ] || [ -z "$INSTANCE_NAME" ]; then
    echo "Error: Could not extract MILLEGRILLES_ROOT or INSTANCE_NAME from $CONFIG_FILE."
    exit 1
fi

echo "[INFO] Using Config: $CONFIG_FILE"
echo "[INFO] Instance:     $INSTANCE_NAME"
echo "[INFO] Root:         $MILLEGRILLES_ROOT"
echo "[INFO] Type:         $NODE_TYPE"

# Ensure destination directory exists
mkdir -p "$DEST_DIR"

# Function to replace placeholders and save to destination
generate_service() {
    local template_file=$1
    local output_file=$2
    
    if [ ! -f "$template_file" ]; then
        echo "Error: Template file $template_file not found."
        exit 1
    fi

    sed -e "s/{{INSTANCE_NAME}}/${INSTANCE_NAME}/g" \
        -e "s/{{MILLEGRILLES_ROOT}}/${MILLEGRILLES_ROOT}/g" \
        -e "s/{{NODE_TYPE}}/${NODE_TYPE}/g" \
        "$template_file" > "$output_file"
}

# Generate certissuer service: ${INSTANCE_NAME}_certissuer.service
generate_service "$TEMPLATE_DIR/certissuer.service.template" "$DEST_DIR/${INSTANCE_NAME}_certissuer.service"

# Generate instance service: ${INSTANCE_NAME}.service
generate_service "$TEMPLATE_DIR/manager.service.template" "$DEST_DIR/${INSTANCE_NAME}_manager.service"

echo ""
echo "Successfully created systemd user services in $DEST_DIR:"
echo "  - ${INSTANCE_NAME}_certissuer.service"
echo "  - ${INSTANCE_NAME}.service"
echo ""
echo "To load the new services, run: systemctl --user daemon-reload"
