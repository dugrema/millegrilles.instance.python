#!/bin/env bash

REP_WORK=`pwd`
STAGING="$REP_WORK/staging"

rm -rf "$STAGING"

REP_ARCHIVES="/mnt/consignation/millegrilles_backup/_ARCHIVES"
APPS=`ls "$REP_ARCHIVES" | awk '{split ($0,a,"."); print a[1]}' | sort -u -`

# Cleanup des vieilles archives. Garder les 2 plus recents fichiers par application.
for APP in ${APPS[@]}; do
  APP_FILES=`ls -r "${REP_ARCHIVES}/${APP}".* | tail -n +3`
  for APP_FILE in ${APP_FILES[@]}; do
    #echo "Supprimer ${APP_FILE}"
    rm "$APP_FILE"
  done
done
