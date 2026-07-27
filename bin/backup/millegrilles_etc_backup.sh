#!/bin/bash
# bin/mongo/millegrilles_etc_backup.sh

set -e

# Load common functions
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SOURCE_DIR}/millegrilles_mongo_common.sh"

usage() {
    echo "Usage: $0 [--out <DIR>]"
    echo "  --out <DIR>        Output directory (default: current directory)"
    exit 1
}

# Initialize variables
OUT_DIR="${MILLEGRILLES_ROOT}/var/backup/etc"

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --out) OUT_DIR="$2"; shift ;;
        *) usage ;;
    esac
    shift
done

# Check requirements
if [ -z "$MILLEGRILLES_ROOT" ] || [ -z "$INSTANCE_NAME" ]; then
    echo "[ERROR] Required environment variables MILLEGRILLES_ROOT or INSTANCE_NAME are not set." >&2
    exit 1
fi

# Prepare output
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="etc_backup_${INSTANCE_NAME}_${TIMESTAMP}.archive.gz"
if [ "$OUT_DIR" != "." ]; then
    OUT_DIR="$(realpath "$OUT_DIR")"
fi
TARGET_FILE="${OUT_DIR}/${BACKUP_NAME}"

mkdir -p "$OUT_DIR"

# Execute mongodump inside a temporary container
echo "[INFO] Running backup ..."

tar --sort=name -C "${MILLEGRILLES_ROOT}" -zcf "${TARGET_FILE}" "etc/"

echo "[SUCCESS] Backup completed: $TARGET_FILE"
