#!/bin/env bash

REP_ETC=$PWD/etc
REP_BIN=$PWD/bin

export REP_ETC REP_BIN

# Charger les variables, paths, users/groups
source ${REP_ETC}/config.env
source ${REP_ETC}/versions.env
source ${REP_BIN}/install_reps.include

if [ -n "${DEV}" ]; then
  export DEV=${DEV}
fi

# Executer le script d'installation de base sans docker
${REP_BIN}/install_instance.sh

if [ -n "${DOCKER}" ]; then
  ${REP_BIN}/install_docker.sh
fi
