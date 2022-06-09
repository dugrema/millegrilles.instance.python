#!/bin/bash

docker swarm leave --force
rm -rf /var/opt/millegrilles/*
docker volume rm mg-redis mongo-data rabbitmq-data nginx-data
