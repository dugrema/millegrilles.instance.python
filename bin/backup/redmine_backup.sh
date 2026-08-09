#!/bin/env bash

REDMINE_BACKUP_FOLDER="${MILLEGRILLES_ROOT}/var/backup/redmine"
WORK_FOLDER="${REDMINE_BACKUP_FOLDER}/work"
if [ ! -d "${REDMINE_FILES}" ]; then
  REDMINE_FILES="${MILLEGRILLES_ROOT}/var/redmine/files"
fi
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="redmine_backup_${INSTANCE_NAME}_${TIMESTAMP}.tar.xz"

# Cleanup from previous sessions
rm "${REDMINE_BACKUP_FOLDER}"/*.work || true
rm -rf "${WORK_FOLDER}"/* || true

mkdir -p "${WORK_FOLDER}" || (echo "Could not create work folder" && exit 1)
# Create symlink to files (included in backup archive)
ln -s "${REDMINE_FILES}" "${WORK_FOLDER}/files"

echo "[INFO] Creating backup of the database"
docker compose -f "${MILLEGRILLES_ROOT}/etc/compose/applications.yml" exec redminemariadb \
  sh -c 'mariadb-dump -u redmine -p"$(cat /run/secrets/mariadb_redmine)" redmine | gzip' > work/backup.redmine.mariadb.sql.gz || exit 2

echo "[INFO] Database backup complete, creating backup archive at ${BACKUP_NAME}"
tar --sort=name -Jchf "${REDMINE_BACKUP_FOLDER}/${BACKUP_NAME}.work" -C "${WORK_FOLDER}" . || exit 3
mv "${REDMINE_BACKUP_FOLDER}/${BACKUP_NAME}.work" "${REDMINE_BACKUP_FOLDER}/${BACKUP_NAME}" || exit 4

echo "[SUCCESS] Redmine database and files backup complete"
rm -rf "${WORK_FOLDER}" || exit 5  # Work folder cleanup
