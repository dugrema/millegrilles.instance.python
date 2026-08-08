#!/bin/env bash

if [ -z "$MILLEGRILLES_ROOT" ]; then
  if [ -z "$1" ]; then
    echo "Provide the path of the MILLEGRILLES_ROOT"
    exit 1
  else
    MILLEGRILLES_ROOT="$1"
  fi
fi

if [ -d "${MILLEGRILLES_ROOT}" ]; then
  if [ ! -f "${MILLEGRILLES_ROOT}/config.env" ]; then
    echo "Configuration file not found: ${MILLEGRILLES_ROOT}/config.env"
    exit 1
  fi
  source "${MILLEGRILLES_ROOT}/config.env"
  echo "THIS WILL DELETE ALL from ${MILLEGRILLES_ROOT} and systemd values of instance ${INSTANCE_NAME}"
  read -p "To proceed, enter y: " response
  if [ "$response" != "y" ]; then
      echo "Operation aborted by user."
      exit 1
  fi
else
  echo "Directory not found: ${MILLEGRILLES_ROOT}"
  exit 1
fi

echo "Removing instance ${INSTANCE_NAME}"

# Gather the units
UNITS=$(systemctl --user list-units --all --type=service,timer,path --no-legend | awk '{print $1}' | grep "^${INSTANCE_NAME}")
echo "[INFO] Disabling and stopping units matching: ${INSTANCE_NAME}"
for unit in $UNITS; do
    echo "Processing $unit..."
    systemctl --user disable --now "$unit"
done
rm "${HOME}/.config/systemd/user/${INSTANCE_NAME}"-*
systemctl --user daemon-reload
echo "[INFO] Systemd cleanup complete."

echo "[INFO] Removing ${MILLEGRILLES_ROOT}/"
rm -rf "${MILLEGRILLES_ROOT}" || exit

echo "[INFO] Removal of instance ${INSTANCE_NAME} successful"
