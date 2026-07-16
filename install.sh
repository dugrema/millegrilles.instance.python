#!/usr/bin/env bash
# Use this script to start the installation process

# Establish installation root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT

# Run the installer
"${REPO_ROOT}/bin/install/install_v2.sh" "$@"
