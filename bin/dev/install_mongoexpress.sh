#!/bin/bash

IMAGE="docker.maceroc.com/mg_mongo_express:0.54_0"

sudo cp mongoexpress.server /var/opt/millegrilles/nginx/modules

# Noms variables
PASSWD_MONGO=passwd.mongo.20230416213544
CERT_MONGO=pki.mongo.cert.20230416220738
KEY_MONGO=pki.mongo.key.20230416220738
CERT_WEB=pki.web.cert.20230311000000
KEY_WEB=pki.web.key.20230311000000

# Constantes
MOTDEPASSE='dummymongo1234'
PASSWD_MONGOEXPRESS=passwd.mongoexpress.20230101000000

# Creer mot de passe web mongo
echo "${MOTDEPASSE}" > /var/opt/millegrilles/secrets/passwd.mongoexpress.txt
echo "${MOTDEPASSE}" | docker secret create ${PASSWD_MONGOEXPRESS} -

docker service create \
  --name mongoexpress \
  --env "ME_CONFIG_BASICAUTH_USERNAME=mongo" \
  --env "ME_CONFIG_MONGODB_ADMINUSERNAME=admin" \
  --env "MONGODB_ADMINPASSWORD_FILE=/run/secrets/mongo.password.txt" \
  --env "ME_CONFIG_BASICAUTH_PASSWORD_FILE=/run/secrets/web.password.txt" \
  --env "VCAP_APP_PORT=443" \
  --env "ME_CONFIG_SITE_SSL_ENABLED='true'" \
  --env "ME_CONFIG_SITE_SSL_CRT_PATH=/run/secrets/web.cert.pem" \
  --env "ME_CONFIG_SITE_SSL_KEY_PATH=/run/secrets/web.key.pem" \
  --env "ME_CONFIG_MONGODB_SERVER=mongo" \
  --env "ME_CONFIG_MONGODB_SSL=true" \
  --env "ME_CONFIG_MONGODB_KEY=/run/secrets/key.pem" \
  --env "ME_CONFIG_MONGODB_CERT=/run/secrets/cert.pem" \
  --env "ME_CONFIG_MONGODB_CACERT=/run/secrets/millegrille.cert.pem" \
  --env "ME_CONFIG_MONGODB_SSLVALIDATE='true'" \
  --config "source=${CERT_MONGO},target=/run/secrets/cert.pem,mode=0444" \
  --config "source=${CERT_WEB},target=/run/secrets/web.cert.pem,mode=0444" \
  --config "source=pki.millegrille,target=/run/secrets/millegrille.cert.pem,mode=0444" \
  --secret "source=${KEY_MONGO},target=key.pem" \
  --secret "source=${KEY_WEB},target=web.key.pem" \
  --secret "source=${PASSWD_MONGO},target=mongo.password.txt" \
  --secret "source=${PASSWD_MONGOEXPRESS},target=web.password.txt" \
  --network name=millegrille_net,alias=mongoexpress \
  "${IMAGE}"

echo "Appliquer nouvelle configuration nginx"
docker service update --force nginx
