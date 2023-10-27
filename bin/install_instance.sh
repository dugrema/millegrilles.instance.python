#!/bin/env bash

REP_BASE=${PWD}
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

dpkg -l python3-pip python3-venv > /dev/null 2> /dev/null
PRESENCE_PACKAGES=$?
if [ "$PRESENCE_PACKAGES" -ne 0 ]; then
  echo "[INFO] Installer packages apt pour python3 venv"
  sudo apt install -y python3-pip python3-venv
fi

if [ ! -d "${PATH_MILLEGRILLES}/configuration" ]; then
  configurer_reps

  echo "[INFO] Creer venv python3 sous $PATH_VENV"
  # URL_MG_MESSAGES="${MG_PIP_REPOSITORY_URL}/${PIP_PACKAGE_MESSAGES}"
  echo "[INFO] Installer millegrilles messages avec url : ${MG_PIP_PACKAGE_URL}"
  sudo -u mginstance ${REP_BIN}/install_python.sh "${PATH_VENV}" "${MG_PIP_PACKAGE_URL}"

  echo "[INFO] Copier fichiers de configuration, code python"
  sudo ${REP_BIN}/install_catalogues.sh

  echo "[INFO] Copier application web"
  sudo ${REP_BIN}/install_web.sh
  sudo chown -R mginstance:millegrilles ${PATH_MILLEGRILLES}/dist

  export PYTHON_BIN=`sudo readlink -f $PATH_MILLEGRILLES/venv/bin/python3`
  sudo setcap 'cap_net_bind_service=+ep' $PYTHON_BIN

  # Installer config pour logging (rsyslog, logrotate)
  sudo cp "${REP_ETC}/01-millegrilles.conf" "/etc/rsyslog.d"
  sudo systemctl restart rsyslog
  sudo cp "${REP_ETC}/logrotate.millegrilles.conf" "/etc/logrotate.d"
fi

echo
echo "[INFO] Installation de base completee OK"
