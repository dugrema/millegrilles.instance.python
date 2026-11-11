#!/bin/env bash

PATH_FILEHOST="$MOUNT_FILEHOST"

if [ -z "$PATH_FILEHOST" ]; then
  PATH_FILEHOST="${MILLEGRILLES_ROOT}/var/filehost"
fi

PATH_BUCKETS="${PATH_FILEHOST}/files/${IDMG}/buckets"

python3 -m millegrilles_messages.backup --verbose verifier --threads 2 \
  --repertoire "$PATH_BUCKETS"
