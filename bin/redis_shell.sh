CONTAINER=$(docker container ls --filter name="-redis-1" -q)
PATH_PASSWD="/run/secrets/passwd.redis.txt"

# PASSWORD=`cat $PATH_PASSWD`
PASSWORD=$(docker exec "$CONTAINER" cat "$PATH_PASSWD")

docker exec -it "$CONTAINER" redis-cli \
  --user client_nodejs -a "$PASSWORD" \
  --tls --cacert /run/secrets/millegrille.cert.pem --cert /run/secrets/cert.pem --key /run/secrets/key.pem
