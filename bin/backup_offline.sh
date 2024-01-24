#!/bin/bash

set -e

ROOT_BACKUP=~/backup/offline
ROOT_WORK=~/work/offline
TIME_TAG=`date +%Y%m%d%H%M`

echo Demarrage backup code pour developpement offline

mkdir -p $ROOT_WORK
mkdir -p $ROOT_BACKUP

# Supprimer les vieilles archives incompletes
rm $ROOT_BACKUP/*.tar* || true

echo Backup des librairies node_modules
tar -zcf $ROOT_WORK/millegrilles.npm.$TIME_TAG.tar.gz \
    /var/lib/jenkins/workspace/*/node_modules/ \
    /var/lib/jenkins/workspace/*/client/node_modules/

echo Backup des libraries cargo

mkdir -p $ROOT_WORK/cargo
find /var/lib/jenkins/workspace -maxdepth 2 -type f -name Cargo.lock \
-exec cargo local-registry --sync {} $ROOT_WORK/cargo/ \;
tar -C $ROOT_WORK -cf $ROOT_WORK/millegrilles.cargo.$TIME_TAG.tar cargo/

echo Backup libraries python

mkdir -p $ROOT_WORK/pip
. ~/venv_offline/bin/activate
find /var/lib/jenkins/workspace -maxdepth 2 -type f -name requirements.txt \
-exec pip download -r {} -d $ROOT_WORK/pip/ \;
tar -C $ROOT_WORK -cf $ROOT_WORK/millegrilles.pip.$TIME_TAG.tar pip/

REP_DOCKER_LISTS=/var/lib/jenkins/workspace/millegrilles.catalogues@2/output
if [ -d $REP_DOCKER_LISTS ]; then
  echo Generer les tarfiles avec images docker de build, catalogues et middleware
  ~/bin/pull_images.sh
  docker image save -o $ROOT_WORK/docker.middleware.$TIME_TAG.tar `cat $REP_DOCKER_LISTS/docker.installation.txt`
  docker image save -o $ROOT_WORK/docker.catalogues.$TIME_TAG.tar `cat $REP_DOCKER_LISTS/docker.catalogues.txt`
  docker image save -o $ROOT_WORK/docker.developpement.$TIME_TAG.tar `cat $REP_DOCKER_LISTS/docker.developpement.txt`
fi

# Supprimer le backup precedent (rotation doit etre faite avant)
rm -r $ROOT_BACKUP
mkdir -p $ROOT_BACKUP

# Copier les fichiers .tar et .tar.gz
cp -rl $ROOT_WORK/*.tar* $ROOT_BACKUP

# CLeanup des tarfiles deja copies
rm $ROOT_WORK/*.tar*

echo Backup complete