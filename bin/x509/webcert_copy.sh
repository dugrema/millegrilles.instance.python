#!/bin/env bash
set -eu

SRC_DIR=/home/acmesh/.acme.sh/live/${INSTANCE_NAME}
DEST_DIR=${MILLEGRILLES_ROOT}/secrets

echo "Copying web key/certs from ${SRC_DIR} to ${DEST_DIR}"
rsync -q --times "${SRC_DIR}"/* "${DEST_DIR}"

echo "Reloading nginx on instance ${INSTANCE_NAME}"
systemctl --user restart ${INSTANCE_NAME}-nginx
