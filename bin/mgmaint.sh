#!/bin/bash

docker container prune -f

docker volume ls -qf dangling=true | \
egrep '([a-z0-9]{32})' | \
while read VOL
do
  docker volume rm $VOL
done

docker image prune -f
