#!/bin/env bash

REP_ETC=./etc
REP_BIN=./bin

echo "[INFO] Preparation d'une instance de base"

# Charger les variables, paths, users/groups
source ${REP_ETC}/config.env
source ${REP_ETC}/versions.env
source ${REP_BIN}/install_reps.include

if [ -n "${DEV}" ]; then
  echo "Inclure DEV overrides"
  source ${REP_ETC}/config.dev
fi

echo
echo "***** ENV ******"
printenv
echo "****************"
echo

if [ ! -d "${PATH_MILLEGRILLES}/configuration" ]; then
  configurer_reps
  echo "Installer packages apt pour python3 venv"
  sudo apt install -y python3-pip python3-venv

  echo "Creer venv python3 sous $PATH_VENV"
  URL_MG_MESSAGES="${MG_PIP_REPOSITORY_URL}/${PIP_PACKAGE_MESSAGES}"
  echo "Installer millegrilles messages avec url : ${URL_MG_MESSAGES}"
  sudo -u mginstance ${REP_BIN}/install_python.sh "${PATH_VENV}" "${URL_MG_MESSAGES}"

  echo "Copier application web"
  sudo -u mginstance ${REP_BIN}/install_web.sh
fi

echo
echo "[INFO] Installation de base sans docker completee OK"
