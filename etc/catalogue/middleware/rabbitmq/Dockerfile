# Use management image for RabbitMQ
FROM rabbitmq:4.3.4-management-alpine

COPY config/rabbitmq.conf /etc/rabbitmq/
COPY config/management.conf /etc/rabbitmq/conf.d/

RUN rabbitmq-plugins enable --offline rabbitmq_auth_mechanism_ssl

EXPOSE 5673
EXPOSE 8443

# CMD /run.sh
# CMD /usr/local/bin/docker-entrypoint.sh
