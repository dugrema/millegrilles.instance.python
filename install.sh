#!/bin/env bash

REP_ETC=$PWD/etc
REP_BIN=$PWD/bin

export REP_ETC REP_BIN

# Charger les variables, paths, users/groups
source ${REP_ETC}/config.env
source ${REP_BIN}/install_reps.include

export MG_INSTALL=1  # Flag d'installation en cours

if [ -n "${DEV}" ]; then
  export DEV=${DEV}
fi

if ! [ -d etc/catalogues/signed ]; then
  echo "Init submodule etc/catalogues"
  git submodule init etc/catalogues
  git submodule update --recursive
fi

# Executer le script d'installation de base sans docker
sudo -H -E ${REP_BIN}/install_instance.sh
${REP_BIN}/install_fixes.sh
