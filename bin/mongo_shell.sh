#!/bin/bash
# bin/mongo_shell.sh

set -e

# Load common functions
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# We might need to adjust the path if bin/backup is the source
if [ ! -f "${SOURCE_DIR}/backup/millegrilles_mongo_common.sh" ]; then
    echo "[ERROR] Could not find millegrilles_mongo_common.sh in ${SOURCE_DIR}/backup/" >&2
    exit 1
fi
source "${SOURCE_DIR}/backup/millegrilles_mongo_common.sh"

# Check requirements
if [ -z "$MILLEGRILLES_ROOT" ] || [ -z "$INSTANCE_NAME" ] || [ -z "$IDMG" ]; then
    echo "[ERROR] Required environment variables MILLEGRILLES_ROOT, INSTANCE_NAME, or IDMG are not set." >&2
    exit 1
fi

if [ ! -f "$MILLEGRILLES_ROOT/secrets/mongo.txt" ]; then
    echo "[ERROR] Password file $MILLEGRILLES_ROOT/secrets/mongo.txt not found." >&2
    exit 1
fi

# Get password and encode it for URI
MONGO_PASSWORD=$(cat "$MILLEGRILLES_ROOT/secrets/mongo.txt")
ENCODED_PASSWORD=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$MONGO_PASSWORD', safe=''))")

MONGO_USER="admin"

# Get the container name
CONTAINER_NAME=$(get_mongo_container_name)
if [ $? -ne 0 ]; then
    exit 1
fi

# Build connection string
# Since we use docker exec, we connect to localhost:27017 inside the container
CONNECTION_STRING="mongodb://${MONGO_USER}:${ENCODED_PASSWORD}@localhost:27017/${IDMG}?authSource=admin&tls=true&tlsCAFile=/run/secrets/millegrille.cert.pem&tlsCertificateKeyFile=/run/secrets/mongo.key_cert.pem"

echo "[INFO] Connecting to MongoDB database: ${IDMG} in container: ${CONTAINER_NAME}"
echo "[INFO] Use 'exit' to quit the shell."

# Execute mongosh inside the running container
docker exec -it "$CONTAINER_NAME" mongosh "$CONNECTION_STRING"
