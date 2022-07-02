#!/bin/env bash
source /var/opt/millegrilles/venv/bin/activate
export PYTHONPATH="${PYTHONPATH}:/var/opt/millegrilles/python"

export CA_PEM=/var/opt/millegrilles/configuration/pki.millegrille.cert
export CERT_PEM=/var/opt/millegrilles/secrets/pki.instance.cert
export KEY_PEM=/var/opt/millegrilles/secrets/pki.instance.key

IMAGE=docker.maceroc.com/millegrilles_messages_python:2022.4.0

docker run --rm \
  -e CA_PEM -e CERT_PEM -e KEY_PEM \
  --mount type=bind,src=/var/opt/millegrilles,target=/var/opt/millegrilles,ro \
  --mount type=volume,src=millegrilles_backup,target=/var/opt/millegrilles_backup \
  $IMAGE \
  -m millegrilles_messages.backup --verbose backup --source /var/opt/millegrilles_backup
