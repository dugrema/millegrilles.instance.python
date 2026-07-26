#!/bin/bash

# bin/millegrilles_mongo_common.sh

get_mongo_container_name() {
    local container
    container=$(docker ps --filter "network=${INSTANCE_NAME}_net" --format "{{.Names}}" | grep mongo | head -n 1)
    
    if [ -z "$container" ]; then
        echo "[ERROR] No mongo container found on network ${INSTANCE_NAME}_net." >&2
        return 1
    fi
    echo "mongo"
}

cleanup() {
    local tmp_dir="$1"
    if [ -d "$tmp_dir" ]; then
        rm -rf "$tmp_dir"
    fi
}
