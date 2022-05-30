#!/bin/bash

docker swarm leave --force
docker network rm millegrille_net
rm -rf /var/opt/millegrilles/*
docker volume rm mg-redis mongo-data rabbitmq-data nginx-data
