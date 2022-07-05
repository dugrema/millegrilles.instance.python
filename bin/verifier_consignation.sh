#!/bin/env bash
source /var/opt/millegrilles/venv/bin/activate
export PYTHONPATH="${PYTHONPATH}:/var/opt/millegrilles/python"

#export CA_PEM=/var/opt/millegrilles/configuration/pki.millegrille.cert
#export CERT_PEM=/var/opt/millegrilles/secrets/pki.instance.cert
#export KEY_PEM=/var/opt/millegrilles/secrets/pki.instance.key
#export MQ_HOSTNAME=localhost

PATH_CONSIGNATION=/var/lib/docker/volumes/millegrilles-consignation/_data/local

python3 -m millegrilles_messages.backup --verbose verifier --repertoire $PATH_CONSIGNATION
