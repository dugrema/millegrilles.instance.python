#!/bin/bash

if [ -f /var/opt/millegrilles/nginx/html ]; then
  echo "[INFO] Correction path nginx/html"
  sudo rm /var/opt/millegrilles/nginx/html
  sudo mkdir -p /var/opt/millegrilles/nginx/html
fi
