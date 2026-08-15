FROM nginx:1.31-alpine3.24

ENV APP_BUNDLE_DIR=/opt/nginx/dist

EXPOSE 80 443
VOLUME /etc/nginx/conf.d /etc/nginx/conf.d/modules /usr/share/nginx/html

COPY res/*.* /etc/nginx/conf.d
COPY bin/40-set-docker-host.sh /docker-entrypoint.d

WORKDIR $APP_BUNDLE_DIR
