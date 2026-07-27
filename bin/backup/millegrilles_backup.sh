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
"${MILLEGRILLES_ROOT}/bin/backup/millegrilles_mongo_backup.sh"
"${MILLEGRILLES_ROOT}/bin/backup/millegrilles_etc_backup.sh"

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

echo "[SUCCESS] Backup job completed"
