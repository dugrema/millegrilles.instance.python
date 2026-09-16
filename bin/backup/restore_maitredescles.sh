#!/bin/env bash

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

docker compose -f "$APP_YAML" down maitredescles
docker compose -f "$APP_YAML" run --rm maitredescles ./millegrilles_maitredescles --restore --capath /var/opt/millegrilles/archives/ca.pem
docker compose -f "$APP_YAML" up -d --remove-orphans maitredescles
