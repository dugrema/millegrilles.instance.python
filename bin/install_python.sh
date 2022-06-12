#!/bin/env bash

PATH_VENV=$1
URL_MGMESSAGES=$2

echo "[INFO] Configurer venv python3, venv et dependances sous ${PATH_VENV}"
python3 -m venv --system-site-packages $PATH_VENV

#PYTHON_BIN=`readlink -f $PATH_VENV/bin/python3`
#sudo setcap 'cap_net_bind_service=+ep' $PYTHON_BIN

echo "Activer venv ${PATH_VENV}"
source "${PATH_VENV}/bin/activate"

echo "Installer pip wheel"
pip3 install wheel

echo "Installer millegrilles messages (path $URL_MGMESSAGES)"
pip3 install $URL_MGMESSAGES

pip3 install -r requirements.txt

echo "[INFO] Fin configuration venv python3"
