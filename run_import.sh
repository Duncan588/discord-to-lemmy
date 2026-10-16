#!/bin/bash
# Run import.py in a throwaway Python container on the compose network.
set -euo pipefail; cd "$(dirname "$0")"
NET=$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' "$(docker compose ps -q postgres)")
docker run --rm --network "$NET" -v "$PWD:/w" -w /w --env-file .env python:3.12-slim \
  sh -c "pip -q install psycopg2-binary >/dev/null 2>&1; python import.py $*"
