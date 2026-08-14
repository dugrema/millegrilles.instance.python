#!/bin/sh

PASSWD=`cat /run/secrets/passwd.redis.txt`

redis-cli \
  --user client_nodejs --pass $PASSWD \
  --tls \
  --cacert /run/secrets/millegrille.cert.pem \
  --cert /run/secrets/cert.pem \
  --key /run/secrets/key.pem
