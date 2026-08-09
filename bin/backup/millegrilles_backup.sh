#!/bin/bash
# bin/backup/millegrilles_backup.sh

set -e

# Ensure MILLEGRILLES_ROOT is set
if [ -z "${MILLEGRILLES_ROOT}" ]; then
    echo "[ERROR] MILLEGRILLES_ROOT is not set. Please ensure it is exported in your environment."
    exit 1
fi

echo "[INFO] Starting backup job"

# Run backup
if [ -f "${MILLEGRILLES_ROOT}/secrets/mongo.txt" ]; then
    echo "[INFO] MongoDB secrets found. Running MongoDB backup..."
    if ! "${MILLEGRILLES_ROOT}/bin/backup/millegrilles_mongo_backup.sh"; then
        echo "[WARN] MongoDB backup failed. Continuing with other backups."
    fi
else
    echo "[INFO] MongoDB not configured (no secrets/mongo.txt). Skipping MongoDB backup."
fi

"${MILLEGRILLES_ROOT}/bin/backup/millegrilles_etc_backup.sh"

if [ -d "${MILLEGRILLES_ROOT}/var/backup/redmine" ]; then
  set +e
  "${MILLEGRILLES_ROOT}/bin/backup/redmine_backup.sh"
  set -e
fi

# Function to rotate backups
# Keeps the $keep most recent files in the specified directory
rotate_backups() {
    local backup_dir="$1"
    local keep="${2:-4}" # Default to 4 if not specified
    
    echo "[INFO] Rotating backups in $backup_dir, keeping last $keep files"
    
    if [ ! -d "$backup_dir" ]; then
        echo "[WARN] Directory $backup_dir does not exist. Skipping rotation."
        return 0
    fi

    # 1. find: find files only (-type f) in the specified directory (-maxdepth 1)
    # 2. printf: print modification time in epoch and the path for reliable sorting
    # 3. sort: sort numerically, descending (newest first)
    # 4. tail: skip the first $keep lines (the $keep newest files)
    # 5. cut: strip the timestamp and leading space to get only the path
    # 6. xargs: delete the files (using -d '\n' for spaces in filenames and -r to avoid error if empty)
    find "$backup_dir" -maxdepth 1 -type f -printf '%T@ %p\n' | \
        sort -rn | \
        tail -n +$((keep + 1)) | \
        cut -d' ' -f2- | \
        xargs -d '\n' -r rm

    echo "[INFO] Rotation completed for $backup_dir"
}

# Rotate backup folders
rotate_backups "${MILLEGRILLES_ROOT}/var/backup/mongo" 4
rotate_backups "${MILLEGRILLES_ROOT}/var/backup/etc" 10
if [ -d "${MILLEGRILLES_ROOT}/var/backup/redmine" ]; then
  rotate_backups "${MILLEGRILLES_ROOT}/var/backup/redmine" 3
fi

if [ -n "${BACKUP_RSYNC_DEST}" ]; then
  echo "[INFO] Synchronizing new backup with rsync to ${BACKUP_RSYNC_DEST}"
  rsync -avr --delete-after "${MILLEGRILLES_ROOT}/var/backup" ${BACKUP_RSYNC_DEST}
fi

echo "[SUCCESS] Backup job completed"
