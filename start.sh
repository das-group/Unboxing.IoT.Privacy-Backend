#!/bin/bash

# stop containers
docker compose down -v --rmi local

# start containers
docker compose up -d --build