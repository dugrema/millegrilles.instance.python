#!/bin/env bash

set -eu

MILLEGRILLES_ROOT=$1

if [ -z "$2" ]; then
  PROJECT_PATH=$2
else
  PROJECT_PATH="$HOME/git/millegrilles.instance.python/"
fi

# Use to activate millegrille venv
. "$MILLEGRILLES_ROOT"/bin/activate.sh
cd "$PROJECT_PATH" || ( echo "Path $PROJECT_PATH not found" && exit 1 )
echo "[INFO] Updating manager"
git pull

echo "[INFO] Updating utilities and compose files"
cp -r "$PROJECT_PATH"/bin/* "$MILLEGRILLES_ROOT"/bin/
cp "$PROJECT_PATH"/etc/compose/coremodules/* "$MILLEGRILLES_ROOT"/etc/compose/coremodules/

echo "[INFO] Updating applications"
bin/manage_apps.py update -i

echo "[INFO] Restarting nginx, middleware and applications as required"
if [ "$SECURITE" != "1.public" ]; then
  systemctl --user stop "$INSTANCE_NAME"-applications
  systemctl --user restart "$INSTANCE_NAME"-middleware
  systemctl --user restart "$INSTANCE_NAME"-applications
  if [ "$SECURITE" != "4.secure" ]; then
    systemctl --user restart "$INSTANCE_NAME"-nginx
  fi
  if [ "$SECURITE" == "3.protege" ] || [ "$SECURITE" != "4.secure" ]; then
    systemctl --user restart "$INSTANCE_NAME"-certissuer
  fi
fi
systemctl --user restart "$INSTANCE_NAME"-manager

# Visual app verification
if [ "$SECURITE" != "1.public" ]; then
  cd "$MILLEGRILLES_ROOT" || exit 1
  printf "\n---------\n[SUCCESS] Update complete, waiting 10 seconds to view status...\n---------\n\n"
  sleep 10  # Give time for the apps to restart
  docker compose -f etc/compose/applications.yml ps
  echo
  if [ "$SECURITE" == "2.prive" ]; then
    docker compose -f etc/compose/middleware/node-prive.yml ps
    echo
    docker compose -f etc/compose/coremodules/nginx.yml ps
    echo
  fi
  if [ "$SECURITE" == "3.protege" ]; then
    docker compose -f etc/compose/middleware/node-protege.yml ps
    echo
    docker compose -f etc/compose/coremodules/nginx.yml ps
    echo
    docker compose -f etc/compose/coremodules/certissuer.yml ps
    echo
  fi
  if [ "$SECURITE" == "4.secure" ]; then
    docker compose -f etc/compose/middleware/node-secure.yml ps
    echo
    docker compose -f etc/compose/coremodules/certissuer.yml ps
    echo
  fi
fi
