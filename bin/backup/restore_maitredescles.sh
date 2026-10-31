#!/bin/env bash

SERVICE_NAME=maitredescles
EXEC_NAME=millegrilles_maitredescles
CA_PATH=/var/opt/millegrilles/archives/ca.pem

export RUST_LOG="error,${EXEC_NAME}=info,millegrilles_common_rust::v3::impls::backup_service=info,millegrilles_common_rust::v3::impls::backup_restorer=info,lapin::channels=off"

NORESUME=

usage() {
    echo "Usage: $0 [--noresume]"
    echo "  --noresume            Truncates all data tables and restores from scratch"
    exit 1
}

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --noresume) NORESUME="--noresume" ;;
        --help) usage ;;
    esac
    shift
done

if [ -z "$MILLEGRILLES_ROOT" ]; then
  echo "The environment has to be activated (MILLEGRILLES_ROOT is empty)"
  exit 1
fi

CA_KEY_PATH="${MILLEGRILLES_ROOT}/var/backup/domains/ca.pem"
# Ensure the ca.pem key is present
if [ ! -f "$CA_KEY_PATH" ]; then
  echo "The ca.pem key must be placed under $CA_KEY_PATH"
  exit 1
fi

APP_YAML="${MILLEGRILLES_ROOT}/etc/compose/applications.yml"

docker compose -f "$APP_YAML" down $SERVICE_NAME
docker compose -f "$APP_YAML" run -e RUST_LOG --rm $SERVICE_NAME ./${EXEC_NAME} --restore $NORESUME --capath "$CA_PATH"
docker compose -f "$APP_YAML" up -d --remove-orphans $SERVICE_NAME
