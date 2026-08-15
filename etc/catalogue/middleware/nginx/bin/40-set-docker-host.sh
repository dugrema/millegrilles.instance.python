#!/bin/sh

INTERNAL_HOST_IP=$(ip route show default | awk '/default/ {print $3}')
echo "${INTERNAL_HOST_IP} docker" >> /etc/hosts
