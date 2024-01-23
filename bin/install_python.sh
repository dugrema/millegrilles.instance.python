#!/bin/env bash

PATH_VENV=$1
# URL_MGMESSAGES=$2

echo "[INFO] Configurer venv python3, venv et dependances sous ${PATH_VENV}"
python3 -m venv --system-site-packages $PATH_VENV

#PYTHON_BIN=`readlink -f $PATH_VENV/bin/python3`
#sudo setcap 'cap_net_bind_service=+ep' $PYTHON_BIN

echo "Activer venv ${PATH_VENV}"
source "${PATH_VENV}/bin/activate"

if ! pip3 list | grep "wheel" > /dev/null; then
  echo "[INFO] Installer pip wheel"
  pip3 install wheel
fi

# Verifier que le package millegrilles-messages de la bonne version est installe
#MGMESSAGES_INSTALLE=0
#if ! pip3 list | grep -e "${MG_PIP_PACKAGE_NAME}" | grep -e "${MG_PIP_PACKAGE_VERSION}" > /dev/null; then
#  echo "[INFO] Installer millegrilles messages (path $MG_PIP_PACKAGE_URL)"
#  pip3 install $URL_MGMESSAGES
#  MGMESSAGES_INSTALLE=1
#fi
cd
echo "[INFO] Verifier requirements python pour millegrilles, installer au besoin"
pip3 install -r requirements.txt

# Fix pour cryptography
# https://stackoverflow.com/questions/74981558/error-updating-python3-pip-attributeerror-module-lib-has-no-attribute-openss
#if [ "${MGMESSAGES_INSTALLE}" -eq 1 ]; then
#  echo "[INFO] Fix installation cryptography"
#  python3 -m pip install -U pyOpenSSL cryptography
#fi

echo "[INFO] Fin configuration venv python3"
