#!/bin/bash
# Convenience script to run the natural20 Docker container

docker build -t natural20:latest .
docker run --env-file=env.list -p 5001:5001 -it natural20:latest "$@"
