#!/bin/bash

docker volume rm \
  millegrilles-consignation millegrilles-staging millegrilles_backup \
  maitredescles-sqlite

sudo rm -rf /var/opt/millegrilles

mgmaint.sh
