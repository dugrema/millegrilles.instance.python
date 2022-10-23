#!/bin/env bash
source /var/opt/millegrilles/venv/bin/activate
export PYTHONPATH="${PYTHONPATH}:/var/opt/millegrilles/python"
export CERTISSUER_URL="http://`hostname --fqdn`:2080"
echo "CERTISSUER_URL $CERTISSUER_URL"
python3 -m millegrilles_instance $@
