#!/bin/env bash
set -euo pipefail

# 1. Setup Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS_DIR="${SCRIPT_DIR}/applications"
BUILD_DIR="${SCRIPT_DIR}/build"
CHECKSUM_FILE="${BUILD_DIR}/sha256sums.txt"

# 2. Dependency Check
for cmd in jq tar sha256sum; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Error: $cmd is required but not installed." >&2
        exit 1
    fi
done

# 3. Handle Arguments
CLEAN=false
for arg in "$@"; do
    if [[ "$arg" == "--clean" ]]; then
        CLEAN=true
    fi
done

# 4. Initialization
if [[ "$CLEAN" = true ]]; then
    echo "Cleaning build directory..."
    rm -rf "${BUILD_DIR}"
fi
mkdir -p "${BUILD_DIR}"
: > "${CHECKSUM_FILE}"

echo "Starting build process..."

# 5. Main Loop
# Iterating through all directories in the applications folder
for app_dir in "${APPS_DIR}"/*; do
    if [[ ! -d "$app_dir" ]]; then
        continue
    fi

    metadata_json="${app_dir}/metadata.json"
    
    if [[ ! -f "$metadata_json" ]]; then
        echo "Warning: Skipping \"$(basename "$app_dir")\" (no metadata.json found)" >&2
        continue
    fi

    # Extract name and version using jq. 
    # // empty ensures we get an empty string if the key is missing.
    APP_NAME=$(jq -r '.name // empty' "$metadata_json")
    APP_VERSION=$(jq -r '.version // empty' "$metadata_json")

    if [[ -z "$APP_NAME" ]] || [[ -z "$APP_VERSION" ]]; then
        echo "Error: Missing 'name' or 'version' in ${metadata_json}" >&2
        continue
    fi

    ARCHIVE_NAME="${APP_NAME}.${APP_VERSION}.tar.gz"
    ARCHIVE_PATH="${BUILD_DIR}/${ARCHIVE_NAME}"

    echo "Building: ${APP_NAME} (v${APP_VERSION}) -> ${ARCHIVE_NAME}"

    # Create the archive. 
    # -C changes to the application directory so that files are at the root of the archive.
    if tar -C "$app_dir" -zcf "$ARCHIVE_PATH" .; then
        # Generate SHA256 checksum and append to the checksum file
        sha256sum "$ARCHIVE_PATH" >> "$CHECKSUM_FILE"
        echo "  [OK] Created ${ARCHIVE_NAME}"
    else
        echo "  [FAILED] Failed to create archive for ${APP_NAME}" >&2
    fi
done

echo "Build process completed. Archives and checksums are in ${BUILD_DIR}/"
