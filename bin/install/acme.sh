#!/bin/env bash

set -eu

echo "Installing acme.sh"

# Note: this installs acme.sh and a cron job to renew the certificates
curl https://get.acme.sh | sh -s email=$EMAIL

mkdir -p ~/".acme.sh/live/${INSTANCE_NAME}"

./acme.sh --issue \
  -d ${INSTANCE_DOMAIN} \
  --webroot "${MILLEGRILLES_ROOT}/var/nginx/html/" \
  --key-file ~/.acme.sh/live/${INSTANCE_NAME}/web.key.pem \
  --fullchain-file ~/.acme.sh/live/${INSTANCE_NAME}/web.cert.pem

# From the instance account
# systemctl --user enable --now webcert_update.path
