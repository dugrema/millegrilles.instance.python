#!/bin/env bash

PATH_VAR_CONFIGURATION_DOCKER="/var/opt/millegrilles/configuration/docker"

PATH_SCRIPT=`readlink -f "$0"`
PATH_DIR_BIN=`dirname "${PATH_SCRIPT}"`
PATH_DIR_INSTALL=`dirname "${PATH_DIR_BIN}"`
PATH_DIR_DOCKER="${PATH_DIR_INSTALL}/etc/docker"
echo "$PATH_DIR_DOCKER"

mkdir -p "${PATH_VAR_CONFIGURATION_DOCKER}"
cp -v ${PATH_DIR_DOCKER}/docker.*.json "${PATH_VAR_CONFIGURATION_DOCKER}"