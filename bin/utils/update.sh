#!/bin/env bash

set -eu

# --- Configuration & Validation ---

# Required arguments
MILLEGRILLES_ROOT="${1:?Error: MILLEGRILLES_ROOT must be provided as the first argument}"

# Optional argument with default
PROJECT_PATH="${2:-$HOME/git/millegrilles.instance.python/}"

# Validate directories
if [ ! -d "$MILLEGRILLES_ROOT" ]; then
  echo "[ERROR] MILLEGRILLES_ROOT '$MILLEGRILLES_ROOT' is not a directory."
  exit 1
fi

if [ ! -d "$PROJECT_PATH" ]; then
  echo "[ERROR] PROJECT_PATH '$PROJECT_PATH' is not a directory."
  exit 1
fi

# --- Update Process ---

# Activate millegrille venv
ACTIVATE_SCRIPT="$MILLEGRILLES_ROOT/bin/activate.sh"
if [ -f "$ACTIVATE_SCRIPT" ]; then
  # shellcheck source=/dev/null
  source "$ACTIVATE_SCRIPT"
else
  echo "[ERROR] Activation script not found at $ACTIVATE_SCRIPT"
  exit 1
fi

# Validate environment variables
if [ -z "${INSTANCE_NAME:-}" ]; then
  echo "[ERROR] INSTANCE_NAME environment variable is not set."
  exit 1
fi

SECURITE="${SECURITE:-unknown}"

# Update project repository
cd "$PROJECT_PATH" || { echo "[ERROR] Could not change directory to $PROJECT_PATH"; exit 1; }

echo "[INFO] Updating manager repository..."
git fetch origin
git reset --hard origin/$(git rev-parse --abbrev-ref HEAD)

echo "[INFO] Updating utilities and compose files..."
# Use cp -a to preserve permissions and ownership
cp -a "$PROJECT_PATH"/bin/* "$MILLEGRILLES_ROOT"/bin/
if [ "$SECURITE" != "1.public" ]; then
  cp -a "$PROJECT_PATH"/etc/compose/coremodules/* "$MILLEGRILLES_ROOT"/etc/compose/coremodules/
fi

echo "[INFO] Updating applications..."
if [ -f "bin/manage_apps.py" ]; then
  bin/manage_apps.py update -i
else
  echo "[ERROR] bin/manage_apps.py not found in $PROJECT_PATH"
  exit 1
fi

echo "[INFO] Restarting services..."
if [ "$SECURITE" != "1.public" ]; then
  echo "[INFO] Stopping applications..."
  systemctl --user stop "$INSTANCE_NAME"-applications

  echo "[INFO] Restarting middleware..."
  systemctl --user restart "$INSTANCE_NAME"-middleware

  echo "[INFO] Restarting applications..."
  systemctl --user restart "$INSTANCE_NAME"-applications

  if [ "$SECURITE" != "4.secure" ]; then
    echo "[INFO] Restarting nginx..."
    systemctl --user restart "$INSTANCE_NAME"-nginx
  fi

  if [ "$SECURITE" == "3.protege" ] || [ "$SECURITE" == "4.secure" ]; then
    echo "[INFO] Restarting certissuer..."
    systemctl --user restart "$INSTANCE_NAME"-certissuer
  fi
fi

echo "[INFO] Restarting manager..."
systemctl --user restart "$INSTANCE_NAME"-manager

# --- Verification ---

if [ "$SECURITE" != "1.public" ]; then
  cd "$MILLEGRILLES_ROOT" || exit 1
  printf "\n---------\n[SUCCESS] Update complete, waiting 10 seconds to verify status...\n---------\n\n"
  sleep 10  # Give time for the apps to restart

  # Helper function for docker status
  print_docker_status() {
    local compose_file="$1"
    local label="$2"
    if [ -f "$compose_file" ]; then
      echo "--- $label ($compose_file) ---"
      docker compose -f "$compose_file" ps
      echo
    else
      echo "[WARNING] Compose file $compose_file not found."
    fi
  }

  print_docker_status "etc/compose/applications.yml" "Applications"

  case "$SECURITE" in
    "2.prive")
      print_docker_status "etc/compose/middleware/node-prive.yml" "Middleware (prive)"
      print_docker_status "etc/compose/coremodules/nginx.yml" "Nginx"
      ;;
    "3.protege")
      print_docker_status "etc/compose/middleware/node-protege.yml" "Middleware (protege)"
      print_docker_status "etc/compose/coremodules/nginx.yml" "Nginx"
      print_docker_status "etc/compose/coremodules/certissuer.yml" "Certissuer"
      ;;
    "4.secure")
      print_docker_status "etc/compose/middleware/node-secure.yml" "Middleware (secure)"
      print_docker_status "etc/compose/coremodules/certissuer.yml" "Certissuer"
      ;;
  esac
fi
