#!/bin/bash

set -e

REP_SRC=./dist/web
REP_INSTALLATION=/var/opt/millegrilles/dist/installation
REP_NGINX_HTML=/var/opt/millegrilles/nginx/html

mkdir -p $REP_INSTALLATION

#./build_src.sh
cp -r $REP_SRC/* $REP_INSTALLATION
cp $REP_SRC/favicon.ico $REP_NGINX_HTML
