#!/bin/bash

#docker service update -d --publish-add 8380:8380 certissuer
# docker service update -d --publish-add published=8443,target=8443,mode=host mq
docker service update -d --publish-add 6379:6379 redis
docker service update -d --publish-add 27017:27017 mongo
docker service update -d --publish-add 3003:443 coupdoeil
docker service update -d --publish-add published=3001,target=1443,mode=host protected_webapi
docker service update -d --publish-add published=3001,target=1443,mode=host private_webapi
docker service update -d --publish-add published=3021,target=1443,mode=host fichiers
docker service update -d --publish-add published=9200,target=9200,mode=host elasticsearch
docker service update -d --publish-add published=3037,target=1443,mode=host collections
docker service update -d --publish-add published=3013,target=1443,mode=host senseurspassifs_web
docker service update -d --publish-add published=3039,target=443,mode=host messagerie_web
docker service update -d --publish-add published=3005,target=1443,mode=host webauthn
docker service update -d --publish-add 10443:443 mongoexpress
docker service update -d --publish-add 8983:8983 solr_server
