#!/usr/bin/env bash

set -e  # Abandonner immediatement pour toute erreur d'execution

source image_info.txt

if [ -z $VERSION ]; then
  echo "Erreur, la version n'est pas inclue dans image_info.txt"
  exit 3
fi

BUILD_FILE=$NAME.$VERSION.tar.gz
BUILD_PATH=$PWD/web

traiter_fichier_react() {
  # Decide si on bati ou telecharge un package pour le build react.
  # Les RPi sont tres lents pour batir le build, c'est mieux de juste recuperer
  # celui qui est genere sur une workstation de developpement.

  ARCH=`uname -m`
  rm -f $NAME.*.tar.gz

  if [ $ARCH == 'x86_64' ] || [ -z $URL_SERVEUR_DEV ]; then
    echo "Architecture $ARCH (ou URL serveur DEV non inclus), on fait un nouveau build React"
    package_build
  else
    echo "Architecture $ARCH, on va chercher le fichier avec le build installation web pour React sur $URL_SERVEUR_DEV"
    telecharger_package
  fi
}

package_build() {
  echo "Building new installation web React app"
  # Sauvegarder information de version
  makeManifest
  npm run-script build

  echo Creer fichier tar $BUILD_PATH/../$BUILD_FILE
  tar -zcf $BUILD_PATH/../$BUILD_FILE build/
  echo Fin creation tar file
}

telecharger_package() {
  cd $BUILD_PATH/..
  sftp ${URL_SERVEUR_DEV}:${PATH_SERVEUR_DEV}/$BUILD_FILE
  if [ $? -ne 0 ]; then
    echo "Erreur download fichier react"
    exit 1
  fi
  echo "Nouvelle version du fichier react telechargee"
}

installer() {
  echo "Installation de l'application deployeur web React dans $BUILD_PATH"
  cd $BUILD_PATH/..
  rm -rf react_build
  mkdir react_build && \
    tar -xf $BUILD_FILE -C react_build
}

makeManifest() {
  cd $BUILD_PATH/..
  source image_info.txt
  cd $BUILD_PATH/src
  DATECOURANTE=`date "+%Y-%m-%d %H:%M"`

  if [ -f manifest.build.js ]; then
    mv manifest.build.js manifest.build.js.cp
  fi

  echo "const build = {" >> manifest.build.js
  echo "  date: '$DATECOURANTE'," >> manifest.build.js
  echo "  version: '$VERSION'" >> manifest.build.js
  echo "}" >> manifest.build.js
  echo "module.exports = build;" >> manifest.build.js
  cd $BUILD_PATH
}

sequence() {
  traiter_fichier_react
  installer
}

sequence
