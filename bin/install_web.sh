#!/bin/bash

set -e

REP_SRC=./dist/web
REP_NGINX_HTML=/var/opt/millegrilles/nginx/html
REP_NGINX_DATA=/var/opt/millegrilles/nginx/data

mkdir -p $REP_NGINX_HTML $REP_NGINX_DATA
cp $REP_SRC/favicon.ico $REP_NGINX_HTML
