#!/bin/env bash

install_docker() {
    if ! docker info > /dev/null 2> /dev/null; then
        echo "[INFO] Installation de docker"
        sudo apt install -y docker.io
        if sudo apt install -y docker.io; then
          echo "[OK] Docker installe"
        else
          echo "[ERREUR] Erreur installation docker"
          exit 1
        fi
    else
        echo "[INFO] docker est deja installe"
    fi
}

configurer_docker() {
  # Installer logging pour docker avec rsyslog
  # Copier fichiers s'ils n'existent pas deja
  sudo cp -n etc/daemon.json /etc/docker
  sudo cp -n etc/logrotate.millegrilles.conf /etc/logrotate.d/millegrilles
  sudo cp -n etc/01-millegrilles.conf /etc/rsyslog.d/

  if ! cat /etc/rsyslog.conf | grep '^input(type="imtcp" port="514")'; then
    echo "[INFO] Ajouter l'option TCP sur port 514 dans /etc/rsyslog.conf"
    sudo cp /etc/rsyslog.conf /etc/rsyslog.conf.old
    echo 'module(load="imtcp")' | sudo tee -a /etc/rsyslog.conf
    echo 'input(type="imtcp" port="514")' | sudo tee -a /etc/rsyslog.conf
  fi
  echo "[INFO] Redemarrer rsyslog"
  sudo systemctl restart rsyslog

  echo "[INFO] Activation du redemarrage automatique de docker"
  sudo systemctl enable docker

  echo "[INFO] Redmarrer docker avec la nouvelle configuration de logging"
  sudo systemctl restart docker
}

# Initialiser swarm
initialiser_swarm() {
  echo "[INFO] Initialiser docker swarm"
  sudo docker swarm init --advertise-addr 127.0.0.1 > /dev/null 2> /dev/null
  resultat=$?
  if [ $resultat -ne 0 ] && [ $resultat -ne 1 ]; then
    echo $resultat
    echo "[ERREUR] Erreur initalisation swarm"
    exit 2
  fi
}

configurer_swarm() {
  echo "[INFO] Configurer docker swarm"
  sudo docker network create -d overlay --attachable --scope swarm millegrille_net
  sudo docker config rm docker.versions 2> /dev/null || true

  FICHIERS_CONFIG=`ls ${REP_ETC}/docker`
  for NOM_FICHIER in ${FICHIERS_CONFIG}; do
    # Retirer extension (.json)
    MODULE=`echo $NOM_FICHIER | cut -f2 -d'.'`
    echo $MODULE
    sudo docker config rm docker.cfg.$MODULE > /dev/null 2> /dev/null || true
    sudo docker config create docker.cfg.${MODULE} $REP_ETC/docker/docker.${MODULE}.json
  done

  echo "[OK] Configuration docker swarm completee"
}

# Executer les fonctions
install_docker
configurer_docker
initialiser_swarm
configurer_swarm
