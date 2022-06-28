#!/usr/bin/env bash

EXIT_CODE=0
REP_BACKUP=/var/opt/millegrilles_backup/redmine_mariadb

echo "[OK] Demarrage script de backup de redmine.mariadb"

export PASSWORD=`cat /run/secrets/mariadb.redmine.txt`
EXIT_CODE=$?
if [ -z $PASSWORD ]; then
  exit 1
fi

mkdir -p $REP_BACKUP

mysqldump -h mariadb -u redmine -p"$PASSWORD" redmine > $REP_BACKUP/backup.redmine_mariadb.sql
EXIT_CODE=$?

echo "[OK] Fin du script de backup de redmine.mariadb"

echo "{\"exit\": $EXIT_CODE}"

exit $EXIT_CODE
