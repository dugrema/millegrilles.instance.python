#!/bin/env bash

source /var/opt/millegrilles/venv/bin/activate
export PYTHONPATH="${PYTHONPATH}:/var/opt/millegrilles/python"

MQ_HOSTNAME=localhost
REDIS_HOSTNAME=localhost

CERT_PEM=/var/opt/millegrilles/secrets/pki.grosfichiers_backend.cert
KEY_PEM=/var/opt/millegrilles/secrets/pki.grosfichiers_backend.cle
REDIS_PASSWORD_PATH=/var/opt/millegrilles/secrets/passwd.redis.txt

export CERT_PEM KEY_PEM MQ_HOSTNAME REDIS_HOSTNAME REDIS_PASSWORD_PATH

python3 -m millegrilles_messages.backup --verbose grosfichiers $@
