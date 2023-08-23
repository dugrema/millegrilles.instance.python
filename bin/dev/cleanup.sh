#!/bin/bash

docker volume rm \
  millegrilles-consignation millegrilles-staging millegrilles_backup \
  maitredescles-sqlite \
  solr-data solr-zookeeper-data solr-zookeeper-datalog

sudo rm -rf /var/opt/millegrilles

mgmaint.sh
