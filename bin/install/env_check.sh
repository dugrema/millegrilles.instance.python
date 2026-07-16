#!/bin/bash

# The list of packages you want to ensure are installed
REQUIRED_PACKAGES=(
    "git"
    "sudo"
    "dpkg"
    "python3-pip"
    "python3-venv"
    "docker.io"
    "docker-compose-v2"
)

MISSING_PACKAGES=()

for pkg in "${REQUIRED_PACKAGES[@]}"; do
    # dpkg-query returns 'ok installed' for properly installed packages
    if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "ok installed"; then
        MISSING_PACKAGES+=("$pkg")
    fi
done

# If the missing packages array is not empty, report them and exit with 1
if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    echo "Error: Missing required packages: ${MISSING_PACKAGES[*]}"
    echo "Run 'sudo bin/install/setup_system.sh' once to install all dependencies."
    exit 1
fi

echo "All required packages are present."

# Ensure the user has access to docker
docker info > /dev/null 2>&1

exit 0

