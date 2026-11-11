#!/bin/env bash

# Script that verifies the file content of a filehost's buckets for a given system (IDMG)
# By default this verifies the files for the local IDMG value.
# Override by providing the full path of the buckets folder (e.g. /path/to/idmg/buckets)

PATH_FILEHOST="$MOUNT_FILEHOST"

if [ -n "$1" ]; then
  PATH_BUCKETS="$1"
else
  if [ -z "$PATH_FILEHOST" ]; then
    PATH_FILEHOST="${MILLEGRILLES_ROOT}/var/filehost"
  fi
  PATH_BUCKETS="${PATH_FILEHOST}/files/${IDMG}/buckets"
fi

python3 -m millegrilles_messages.backup --verbose verifier --threads 2 \
  --repertoire "$PATH_BUCKETS"
