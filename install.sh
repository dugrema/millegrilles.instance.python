#!/bin/bash

PATH_MILLEGRILLES=/var/opt/millegrilles
PATH_VENV=/var/opt/millegrilles/venv
MG_PIP_REPOSITORY_URL=https://pip.maceroc.com/

PACKAGE_MESSAGES=dist/millegrilles.messages-2022.3.0.tar.gz

echo "Installer packages apt"
sudo apt install -y python3-pip python3-venv

if [ ! -d "$PATH_VENV" ]; then
  echo "Creer venv python3 sous $PATH_VENV"
  python3 -m venv $PATH_VENV
fi

echo "Installer pip requirements.txt"
pip3 install wheel

pip3 install "$MG_PIP_REPOSITORY_URL/$PACKAGE_MESSAGES"
