#!/bin/bash

# git pull to update the repository
git pull

# stop containers
docker compose down -v --rmi local

# start containers
docker compose up -d --build