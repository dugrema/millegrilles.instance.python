#!/bin/env bash

REP_BASE=${PWD}
REP_ETC=./etc
REP_BIN=./bin

configurer_docker() {
  echo "[INFO] Configurer et redemarrer docker et le logging MilleGrilles"

  # Installer logging pour docker avec rsyslog
  # Copier fichiers s'ils n'existent pas deja
  sudo cp -n etc/daemon.json /etc/docker
  sudo cp -n etc/logrotate.millegrilles.conf /etc/logrotate.d/millegrilles
  sudo cp -n etc/01-millegrilles.conf /etc/rsyslog.d/

  if ! cat /etc/rsyslog.conf | grep '^input(type="imtcp" port="514")'; then
    echo "[INFO] Ajouter l'option TCP sur port 514 dans /etc/rsyslog.conf"
    sudo cp /etc/rsyslog.conf /etc/rsyslog.conf.old
    echo '# Ajoute pour MilleGrilles ' | tee -a /etc/rsyslog.conf
    echo 'module(load="imtcp")' | tee -a /etc/rsyslog.conf
    echo 'input(type="imtcp" port="514")' | tee -a /etc/rsyslog.conf
  fi

  echo "[INFO] Redemarrer rsyslog"
  sudo systemctl restart rsyslog

  echo "[INFO] Activation du redemarrage automatique de docker"
  sudo systemctl enable docker

  echo "[INFO] Redmarrer docker avec la nouvelle configuration de logging"
  sudo systemctl restart docker
}

echo "[INFO] Preparation d'une instance de base"

# Charger les variables, paths, users/groups
source ${REP_ETC}/config.env
source ${REP_ETC}/versions.env
source ${REP_BIN}/install_reps.include

echo
echo "***** ENV ******"
printenv
echo "****************"
echo

dpkg -l python3-pip python3-venv > /dev/null 2> /dev/null
PRESENCE_PACKAGES=$?
if [ "$PRESENCE_PACKAGES" -ne 0 ]; then
  echo "[INFO] Installer packages apt pour python3 venv"
  apt install -y python3-pip python3-venv
fi

if [ ! -d "${PATH_MILLEGRILLES}/configuration" ]; then
  configurer_reps

  echo "[INFO] Creer venv python3 sous $PATH_VENV"
  cd "${REP_BASE}" || exit 10
  sudo -E -u mginstance ${REP_BIN}/install_python.sh "${PATH_VENV}"

  echo "[INFO] Copier fichiers de configuration, code python"
  ${REP_BIN}/install_catalogues.sh

  echo "[INFO] Copier application web"
  ${REP_BIN}/install_web.sh
  chown -R mginstance:millegrilles ${PATH_MILLEGRILLES}/dist

  # Permettre a python d'ouvrir un serveur sur les ports < 1024 pour tous les usagers
  export PYTHON_BIN=`readlink -f $PATH_MILLEGRILLES/venv/bin/python3`
  setcap 'cap_net_bind_service=+ep' $PYTHON_BIN

  docker info
  if [ "$?" -eq "0" ]; then
    echo "[INFO] Installer configuration docker pour ipv6"
    configurer_docker
  fi

  # Installer config pour logging (rsyslog, logrotate)
  # Les fichiers ne sont pas modifies s'ils existent deja
  cp -n "${REP_ETC}/01-millegrilles.conf" "/etc/rsyslog.d"
  cp -n "${REP_ETC}/logrotate.millegrilles.conf" "/etc/logrotate.d"
  systemctl restart rsyslog

fi

echo
echo "[INFO] Installation de base completee OK"
