#!/bin/env bash

set -eu

SRC_FILE="${MILLEGRILLES_ROOT}/var/backup/redmine/mariadb/backup.redmine.mariadb.sql.gz"

if [ ! -f "$SRC_FILE" ]; then
  echo "Source file not found. Ensure the file backup.redmine.mariadb.sql.gz is in the ${MILLEGRILLES_ROOT}/var/backup/redmine/mariadb folder."
  exit 1
fi

docker compose -f "${MILLEGRILLES_ROOT}/etc/compose/applications.yml" exec redminemariadb \
  sh -c 'zcat /backup/backup.redmine.mariadb.sql.gz | mariadb -u redmine -p"$(cat /run/secrets/mariadb_redmine)" redmine'

echo "[INFO] Redmine database restored successfully in MariaDB"

REDMINE_FOLDER=${REDMINE_FILES}
if [ -z "$REDMINE_FOLDER" ]; then
  REDMINE_FOLDER="${MILLEGRILLES_ROOT}/var/redmine/files"
fi

echo "[INFO] You can now copy the redmine files to the redmine folder: ${REDMINE_FOLDER}"
