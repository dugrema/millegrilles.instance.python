#!/bin/bash

set -e

REP_SRC=./dist/web
REP_INSTALLATION=/var/opt/millegrilles/dist/installation

mkdir -p $REP_INSTALLATION

#./build_src.sh
cp -r $REP_SRC/* $REP_INSTALLATION
