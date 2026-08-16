#!/usr/bin/env bash
# Use this script to start the installation process

# Establish installation root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT

# Find the type of instance, copy args to avoid consuming them
args=("$@")
TYPE=""
i=0
while [[ $i -lt ${#args[@]} ]]; do
  case "${args[$i]}" in
    --type)
      # The value is the next element in the array
      TYPE="${args[$((i+1))]}"
      ((i+=2))
      ;;
    *)
      ((i++))
      ;;
  esac
done

echo "TYPE FOUND: $TYPE"

# Run the installer with docker support
if [ "$TYPE" == "public" ]; then
  "${REPO_ROOT}/bin/install/install_bare.sh" "$@"
else
  "${REPO_ROOT}/bin/install/install_wdocker.sh" "$@"
fi
