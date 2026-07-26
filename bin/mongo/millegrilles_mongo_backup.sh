#!/bin/bash
# bin/mongo/millegrilles_mongo_backup.sh

set -e

# Load common functions
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SOURCE_DIR}/millegrilles_mongo_common.sh"

usage() {
    echo "Usage: $0 [--domain <DOMAIN>] [--out <DIR>]"
    echo "  --domain <DOMAIN>  Backup only collections starting with DOMAIN/"
    echo "  --out <DIR>        Output directory (default: current directory)"
    exit 1
}

# Initialize variables
DOMAIN=""
OUT_DIR="."

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --domain) DOMAIN="$2"; shift ;;
        --out) OUT_DIR="$2"; shift ;;
        *) usage ;;
    esac
    shift
done

# Check requirements
if [ -z "$MILLEGRILLES_ROOT" ] || [ -z "$INSTANCE_NAME" ] || [ -z "$IDMG" ]; then
    echo "[ERROR] Required environment variables MILLEGRILLES_ROOT, INSTANCE_NAME, or IDMG are not set." >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "[ERROR] docker command not found. Please install docker." >&2
    exit 1
fi

if [ ! -f "$MILLEGRILLES_ROOT/secrets/mongo.txt" ]; then
    echo "[ERROR] Password file $MILLEGRILLES_ROOT/secrets/mongo.txt not found." >&2
    exit 1
fi

# Prepare output
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="mongo_backup_${INSTANCE_NAME}_${TIMESTAMP}.archive.gz"
if [ "$OUT_DIR" != "." ]; then
    OUT_DIR="$(realpath "$OUT_DIR")"
fi
TARGET_FILE="${OUT_DIR}/${BACKUP_NAME}"

mkdir -p "$OUT_DIR"

# Get password and encode it for URI
MONGO_PASSWORD=$(cat "$MILLEGRILLES_ROOT/secrets/mongo.txt")
ENCODED_PASSWORD=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$MONGO_PASSWORD', safe=''))")

MONGO_USER="admin"
CONTAINER_NAME="mongo_backup_container_${TIMESTAMP}"

# Build connection string
CONNECTION_STRING="mongodb://${MONGO_USER}:${ENCODED_PASSWORD}@mongo:27017/?authSource=admin&tls=true&tlsCAFile=/etc_millegrille/millegrille.pem&tlsCertificateKeyFile=/secrets/mongo.pem"

# Determine dump command
if [ -n "$DOMAIN" ]; then
    echo "[INFO] Domain filter applied: $DOMAIN"
    DUMP_CMD="mongodump --uri='${CONNECTION_STRING}' --db '${IDMG}' --nsInclude='${IDMG}.${DOMAIN}/.*' --archive='/dump/backup.archive.gz' --gzip"
else
    echo "[INFO] Full database backup."
    DUMP_CMD="mongodump --uri='${CONNECTION_STRING}' --db '${IDMG}' --archive='/dump/backup.archive.gz' --gzip"
fi

# Execute mongodump inside a temporary container
echo "[INFO] Running mongodump in Docker..."
CONTAINER_ID=$(docker run -d --name "$CONTAINER_NAME" --network "${INSTANCE_NAME}_net" \
    -v "$MILLEGRILLES_ROOT/etc:/etc_millegrille:ro" \
    -v "$MILLEGRILLES_ROOT/secrets:/secrets:ro" \
    -v "$OUT_DIR:/dump" \
    mongo:latest sleep infinity)

if ! docker exec "$CONTAINER_ID" bash -c "$DUMP_CMD"; then
    echo "[ERROR] mongodump failed."
    docker stop "$CONTAINER_ID" > /dev/null || true
    docker rm "$CONTAINER_ID" > /dev/null || true
    exit 1
fi

# Copy the archive from the container to the host
docker cp "$CONTAINER_ID:/dump/backup.archive.gz" "$TARGET_FILE"

# Cleanup container
docker stop "$CONTAINER_ID" > /dev/null
docker rm "$CONTAINER_ID" > /dev/null

echo "[SUCCESS] Backup completed: $TARGET_FILE"
