#!/bin/bash

# Exit immediately if a command exits with a non-zero status,
# if an unset variable is used, or if any part of a pipeline fails.
set -euo pipefail

# Function to display usage instructions
usage() {
    echo "Usage: $0 <url> [destination_dir] [expected_sha256]"
    echo ""
    echo "Arguments:"
    echo "  url                The URL of the .tar.gz file to download."
    echo "  destination_dir    The directory to extract into (default: current directory)."
    echo "  expected_sha256    The SHA256 hash to verify against (optional)."
    echo ""
    echo "Example:"
    echo "  $0 https://example.com/file.tar.gz ./my_folder"
    echo "  $0 https://example.com/file.tar.gz ./my_folder abc123hash..."
    exit 1
}

# Check for minimum required argument
if [ $# -lt 1 ]; then
    usage
fi

# Assign arguments to variables
URL="$1"
DEST_DIR="${2:-.}"
EXPECTED_HASH="${3:-}"

if [ -e "${DEST_DIR}" ]; then
  echo "Destination path already exists"
  exit 2
fi

# Dependencies check
for cmd in curl tar sha256sum awk; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "Error: Required command '$cmd' is not installed." >&2
        exit 1
    fi
done

# Create destination directory if it doesn't exist
mkdir -p "$DEST_DIR"

# Create a temporary file to store the calculated hash
HASH_TMP=$(mktemp)
# Ensure the temporary file is cleaned up on exit
trap 'rm -f "$HASH_TMP"' EXIT

echo "-------------------------------------------------------"
echo "Downloading: $URL"
echo "Extracting to: $DEST_DIR"
echo "-------------------------------------------------------"

# The Core Pipeline:
# 1. curl -fL: Download, fail on HTTP errors, follow redirects.
# 2. tee >(tar ...): Split the stream. One side goes to tar for extraction.
# 3. sha256sum: Calculate the hash of the stream.
# 4. > "$HASH_TMP": Save the hash result to a temporary file.
if ! curl -fL "$URL" | tee >(tar -xzC "$DEST_DIR") | sha256sum > "$HASH_TMP"; then
    echo "Error: Download or extraction failed." >&2
    exit 1
fi

# Extract just the hash value from the sha256sum output (ignores the filename part)
CALCULATED_HASH=$(awk '{print $1}' "$HASH_TMP")

if [ -z "$EXPECTED_HASH" ]; then
    # No hash provided, just print the result
    echo "Download complete."
    echo "SHA256: $CALCULATED_HASH"
else
    # Verify the provided hash
    if [ "$CALCULATED_HASH" == "$EXPECTED_HASH" ]; then
        echo "✅ Verification Successful!"
        echo "SHA256: $CALCULATED_HASH"
    else
        echo "❌ Verification FAILED!"
        echo "  Expected: $EXPECTED_HASH"
        echo "  Actual:   $CALCULATED_HASH"
        rm -r "$DEST_DIR"  # Remove dir, the file is wrong
        exit 1
    fi
fi
