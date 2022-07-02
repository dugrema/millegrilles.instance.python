#!/bin/env bash

DEST_RSYNC="mg-int1:backup"

echo "Copie fichiers staging"
sudo /usr/local/bin/millegrilles_backup_staging.sh

echo "Debut rsync"
rsync -r --delete-after staging/* "$DEST_RSYNC"

echo "rsync complete, cleanup staging"
sudo /usr/local/bin/millegrilles_backup_staging_cleanup.sh
