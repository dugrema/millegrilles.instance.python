#!/bin/env bash
. etc/config.env

set -e

echo "[INFO] Copier fichier web"
PATH_VAR_CONFIGURATION_DOCKER="/var/opt/millegrilles/configuration/docker"
PATH_VAR_CONFIGURATION_CATALOGUES="/var/opt/millegrilles/configuration/catalogues"
PATH_VAR_CONFIGURATION_NGINX="/var/opt/millegrilles/configuration/nginx"
PATH_VAR_CONFIGURATION_PYTHON="/var/opt/millegrilles/python"

PATH_SCRIPT=`readlink -f "$0"`
PATH_DIR_BIN=`dirname "${PATH_SCRIPT}"`
PATH_DIR_INSTALL=`dirname "${PATH_DIR_BIN}"`
PATH_DIR_DOCKER="${PATH_DIR_INSTALL}/etc/docker"
PATH_DIR_INSTANCE="${PATH_DIR_INSTALL}/millegrilles_instance"
echo "$PATH_DIR_DOCKER"

sudo -u mginstance mkdir -p "${PATH_VAR_CONFIGURATION_DOCKER}"
sudo cp -v ${PATH_DIR_DOCKER}/docker.*.json "${PATH_VAR_CONFIGURATION_DOCKER}"
sudo chown mginstance:millegrilles "${PATH_VAR_CONFIGURATION_DOCKER}"

PATH_DIR_CATALOGUES="${PATH_DIR_INSTALL}/etc/catalogues/signed"
sudo -u mginstance mkdir -p "${PATH_VAR_CONFIGURATION_CATALOGUES}"
sudo cp -v ${PATH_DIR_CATALOGUES}/*.json.xz "${PATH_VAR_CONFIGURATION_CATALOGUES}"
sudo chown mginstance:millegrilles "${PATH_VAR_CONFIGURATION_CATALOGUES}"

PATH_DIR_NGINX="${PATH_DIR_INSTALL}/etc/nginx"
echo "$PATH_DIR_NGINX"
sudo -u mginstance mkdir -p "${PATH_VAR_CONFIGURATION_NGINX}"
sudo cp -rv ${PATH_DIR_NGINX}/* "${PATH_VAR_CONFIGURATION_NGINX}"
sudo chown mginstance:millegrilles "${PATH_VAR_CONFIGURATION_NGINX}"

echo "Copier python instance"
sudo mkdir -p ${PATH_VAR_CONFIGURATION_PYTHON}
sudo cp -rv ${PATH_DIR_INSTANCE} ${PATH_VAR_CONFIGURATION_PYTHON}
sudo chown -R mginstance:millegrilles ${PATH_VAR_CONFIGURATION_PYTHON}

echo "Mettre a jour millegrilles-messages avec ${MG_PIP_PACKAGE_URL}"
sudo -i -u mginstance bash -c ". /var/opt/millegrilles/venv/bin/activate; pip3 install --upgrade -i https://millegrilles.mdugre.info/python/dist millegrilles_messages"

echo "[INFO] Fichier configurations copies OK"
