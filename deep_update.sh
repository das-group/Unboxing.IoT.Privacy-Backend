#!/bin/bash

# git pull to update the repository
git pull

# stop containers
docker compose down -v --rmi local

# rebuild images without cache
docker compose build --no-cache

# start containers
docker compose up -d --build
