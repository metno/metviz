#!/bin/bash


export SERVICE_NAME=$1
export DOMAIN1=$1.wps.met.no

export SERVICE_NAME=$1
export DOMAIN2=$2.wps.met.no

export DOMAIN3=$3.wps.met.no

# Signing key for the download/export pipeline (ncapp + worker must share it,
# and it must stay stable across redeploys or in-flight download links break).
# Honour an already-exported value; otherwise generate once and persist outside
# the repo so the same key is reused on every run (and never committed to git).
if [ -z "$DOWNLOAD_SIGNING_KEY" ]; then
  KEY_FILE="$HOME/.metviz_download_signing_key"
  if [ ! -f "$KEY_FILE" ]; then
    openssl rand -hex 32 > "$KEY_FILE"
    chmod 600 "$KEY_FILE"
  fi
  export DOWNLOAD_SIGNING_KEY="$(cat "$KEY_FILE")"
fi

docker stack rm $1
sleep 10
export NODE_ID=$(docker info -f '{{.Swarm.NodeID}}')
docker node update --label-add $1.$1-data=true $NODE_ID
sleep 5
docker stack deploy -c $1.yml $1