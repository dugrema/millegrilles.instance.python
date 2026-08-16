#!/usr/bin/env bash
# Use this script to start the installation process

# Establish installation root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT

# Run the installer with docker support
"${REPO_ROOT}/bin/install/install_wdocker.sh" "$@"
