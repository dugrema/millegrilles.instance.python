#!/bin/env bash

REPSRC=("/mnt/consignation/millegrilles_backup/_ARCHIVES/" \
"/mnt/consignation/millegrilles-consignation/backup/" \
"/mnt/consignation/millegrilles-consignation/local/")

REPDST="/mnt/consignation/snapshot"

mkdir -p "$REPDST/snapshot.new"

for REP in "${REPSRC[@]}"; do
  echo Repertoire $REP
  cp -rl "$REP" "$REPDST/snapshot.new"
done

rm -rf "$REPDST/snapshot.3"
mv "$REPDST/snapshot.2"  "$REPDST/snapshot.3"
mv "$REPDST/snapshot.1"  "$REPDST/snapshot.2"
mv "$REPDST/snapshot.current"  "$REPDST/snapshot.1"
mv "$REPDST/snapshot.new" "$REPDST/snapshot.current"
