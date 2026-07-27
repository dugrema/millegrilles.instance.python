#!/bin/bash
# bin/millegrilles_mongo_restore.sh

set -e

# Load common functions
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SOURCE_DIR}/millegrilles_mongo_common.sh"

usage() {
    echo "Usage: $0 --file <FILE> [--domain <DOMAIN>]"
    echo "  --file <FILE>      ARCHIVE file to restore"
    echo "  --domain <DOMAIN>  Restore only collections starting with DOMAIN/"
    exit 1
}

# Initialize variables
DOMAIN=""
RESTORE_FILE=""

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --file) RESTORE_FILE="$2"; shift ;;
        --domain) DOMAIN="$2"; shift ;;
        *) usage ;;
    esac
    shift
done

# Check requirements
if [ -z "$MILLEGRILLES_ROOT" ] || [ -z "$INSTANCE_NAME" ] || [ -z "$IDMG" ]; then
    echo "[ERROR] Required environment variables MILLEGRILLES_ROOT, INSTANCE_NAME, or IDMG are not set." >&2
    exit 1
fi

if [ -z "$RESTORE_FILE" ]; then
    usage
fi

if [ ! -f "$RESTORE_FILE" ]; then
    echo "[ERROR] Restore file $RESTORE_FILE not found." >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "[ERROR] docker command not found. Please install docker." >&2
    exit 1
fi

# Prepare output
MONGO_PASSWORD=$(cat "$MILLEGRILLES_ROOT/secrets/mongo.txt")
ENCODED_PASSWORD=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$MONGO_PASSWORD', safe=''))")

MONGO_CONTAINER=$(get_mongo_container_name)
if [ $? -ne 0 ]; then
    exit 1
fi

# Build connection string
CONNECTION_STRING="mongodb://admin:${ENCODED_PASSWORD}@${MONGO_CONTAINER}:27017/?authSource=admin&tls=true&tlsCAFile=/etc_millegrille/millegrille.pem&tlsCertificateKeyFile=/secrets/mongo.pem"

# Execute mongorestore inside a container
echo "[INFO] Running mongorestore in Docker..."
if [ -n "$DOMAIN" ]; then
    echo "[INFO] Domain filter applied: $DOMAIN"
    RESTORE_CMD="mongorestore --uri='${CONNECTION_STRING}' --nsInclude='${IDMG}\.${DOMAIN}/*' --drop --gzip --archive='/dump_restore/backup.archive.gz'"
else
    echo "[INFO] Full database restore."
    RESTORE_CMD="mongorestore --uri='${CONNECTION_STRING}' --nsInclude='${IDMG}.*' --drop --gzip --archive='/dump_restore/backup.archive.gz'"
fi

docker run --rm \
    --network "${INSTANCE_NAME}_net" \
    -v "$MILLEGRILLES_ROOT/etc:/etc_millegrille:ro" \
    -v "$MILLEGRILLES_ROOT/secrets:/secrets:ro" \
    -v "$(realpath $RESTORE_FILE):/dump_restore/backup.archive.gz:ro" \
    mongo:latest \
    bash -c "$RESTORE_CMD" || { echo "[ERROR] mongorestore failed."; exit 1; }

# Cleanup
docker volume rm "$VOLUME_NAME" > /dev/null

echo "[SUCCESS] Restore completed."
