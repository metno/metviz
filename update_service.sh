#!/bin/bash


export SERVICE_NAME=$1
export DOMAIN=$1.wps.met.no

docker stack rm $1
sleep 10
export NODE_ID=$(docker info -f '{{.Swarm.NodeID}}')
docker node update --label-add $1.$1-data=true $NODE_ID
sleep 5
docker stack deploy -c $1.yml $1