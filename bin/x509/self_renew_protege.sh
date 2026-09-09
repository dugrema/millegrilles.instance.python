#!/bin/env bash

# Use this file to renew a 3.protege manager (this includes managers for the 4.secure environment)

if [ -z "$INSTANCE_ID" ]; then
  echo "Load the environment first"
  exit 1
fi

"${MILLEGRILLES_ROOT}"/bin/x509/sign_protege.py \
  --millegrilles-root "${MILLEGRILLES_ROOT}" \
  --ca-pem "${MILLEGRILLES_ROOT}/secrets/certissuer/signing_ca.pem" \
  --instance-id $INSTANCE_ID
