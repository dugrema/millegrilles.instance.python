#!/usr/bin/env bash

EXIT_CODE=0
REP_BACKUP=/var/opt/millegrilles_backup/redmine_mariadb

echo "[OK] Demarrage script de backup de redmine files"

mkdir -p $REP_BACKUP

cd /usr/src/redmine/files/
tar c -f $REP_BACKUP/backup.redmine.files.tar *
EXIT_CODE=$?

echo "[OK] Fin du script de backup de redmine files"
echo "{\"exit\": $EXIT_CODE}"

exit $EXIT_CODE

