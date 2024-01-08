#!/bin/env bash

REP_ETC=$PWD/etc
REP_BIN=$PWD/bin

export REP_ETC REP_BIN

# Charger les variables, paths, users/groups
source ${REP_ETC}/config.env
# source ${REP_ETC}/versions.env
source ${REP_BIN}/install_reps.include

if [ -n "${DEV}" ]; then
  export DEV=${DEV}
fi

sudo echo "[INFO] Verification sudo"

git submodule init etc/catalogues
git submodule update --recursive

# Executer le script d'installation de base sans docker
${REP_BIN}/install_instance.sh
${REP_BIN}/install_fixes.sh

# Note : docker est maintenant gere via python dans mginstance
#if [ -n "${DOCKER}" ]; then
#  ${REP_BIN}/install_docker.sh
#fi
