FROM redis:8.10.0-alpine

COPY redis.conf /usr/local/etc/
COPY creer_acl.sh start.sh connect.sh /usr/local/bin/

CMD ["start.sh"]
