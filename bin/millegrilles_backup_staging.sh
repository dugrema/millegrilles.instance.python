#!/bin/env bash

VOLS=/var/lib/docker/volumes
TRANSACTIONS="$VOLS/millegrilles-consignation/_data/backup/transactions"
CONSIGNATION="$VOLS/millegrilles-consignation/_data/local"
APPS="$VOLS/millegrilles_backup/_data/_ARCHIVES"

if [ -z $1 ]; then
  echo "Fournir repertoire work"
  exit 1
fi

REP_WORK=$1
STAGING="$REP_WORK/staging"

mkdir -p "$STAGING"

cp -rl "$TRANSACTIONS" "$STAGING/"
cp -rl "$CONSIGNATION" "$STAGING/"
cp -rl "$APPS" "$STAGING/"