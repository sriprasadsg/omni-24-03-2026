#!/bin/bash
# Run this script to get the current SHA256 digests for pinning Docker images.
# Replace the tags in docker-compose.yml and Dockerfiles with the digest form:
#   image: mongo:8.0@sha256:<digest>
set -e
echo "Fetching Docker image digests for pinning..."
for image in "mongo:8.0" "redis:8.0-alpine" "node:24-alpine" "python:3.13-slim" "nginx:1.27-alpine"; do
    echo -n "$image -> "
    docker pull "$image" --quiet 2>/dev/null
    docker inspect --format='{{index .RepoDigests 0}}' "$image" 2>/dev/null || echo "(pull docker image first)"
done
echo ""
echo "Update docker-compose.yml and Dockerfiles with the digests above."
echo "Format: image: <name>:<tag>@sha256:<digest>"
