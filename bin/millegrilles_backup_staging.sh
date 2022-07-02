#!/bin/env bash

DEST_BACKUP=/var/opt/millegrilles_backup
VOL_CONSIGNATION=/var/lib/docker/volumes/millegrilles-consignation/_data/backup/transactions

rm -rf "$DEST_BACKUP/archive.2"
mv "$DEST_BACKUP/archive.1" "$DEST_BACKUP/archive.2"
mv "$DEST_BACKUP/courant" "$DEST_BACKUP/archive.1"

mkdir -p "$DEST_BACKUP/courant"

cd "$VOL_CONSIGNATION"
tar -cf "$DEST_BACKUP/courant/transactions.tar" ./*
