#!/bin/bash
set -e

# Usage: ./install_webapp.sh <url> <destination_dir> [expected_hash]
URL=$1
DEST_DIR=$2
EXPECTED_HASH=$3

if [ -z "$URL" ] || [ -z "$DEST_DIR" ]; then
  echo "Usage: $0 <url> <destination_dir> [expected_hash]"
  exit 1
fi

mkdir -p "$DEST_DIR"
TEMP_DIR=$(mktemp -d)

echo "Downloading $URL..."
curl -sL "$URL" -o "$TEMP_DIR/package.tar.gz"

if [ -n "$EXPECTED_HASH" ]; then
  echo "Verifying hash..."
  ACTUAL_HASH=$(sha256sum "$TEMP_DIR/package.tar.gz" | awk '{ print $1 }')
  if [ "$ACTUAL_HASH" != "$EXPECTED_HASH" ]; then
    echo "Error: Hash mismatch!"
    echo "Expected: $EXPECTED_HASH"
    echo "Actual:   $ACTUAL_HASH"
    rm -rf "$TEMP_DIR"
    exit 1
  fi
fi

echo "Extracting package..."
tar -xzf "$TEMP_DIR/package.tar.gz" -C "$DEST_DIR" --strip-components=1

rm -rf "$TEMP_DIR"
