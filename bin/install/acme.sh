#!/bin/env bash

set -eu

echo "Installing acme.sh"

# Note: this installs acme.sh and a cron job to renew the certificates
curl https://get.acme.sh | sh -s email=$EMAIL

mkdir -p $HOME/live/${INSTANCE_NAME}

EXPOSE_SCRIPT="${HOME}/live/expose.sh"
# Add script live/expose.sh
{
  echo "chmod 640 ${HOME}/live/*/*.pem"
} > "${EXPOSE_SCRIPT}"
chmod 750 "${EXPOSE_SCRIPT}"

./acme.sh --issue \
  -d ${INSTANCE_DOMAIN} \
  --webroot "/var/www/html/" \
  --key-file "${HOME}/live/${INSTANCE_NAME}/web.key.pem" \
  --fullchain-file "${HOME}/live/${INSTANCE_NAME}/web.cert.pem" \
  --post-hook "${EXPOSE_SCRIPT}"

# From the instance account
# systemctl --user enable --now webcert_update.path
