#!/bin/bash
# Render lemmy.hjson from .env, fix volume perms, start stack, lock instance down.
set -euo pipefail; cd "$(dirname "$0")"
set -a; . ./.env; set +a
umask 077; envsubst < lemmy.hjson.template > lemmy.hjson
mkdir -p volumes/pictrs volumes/postgres data
sudo chown -R 991:991 volumes/pictrs || echo "WARN: chown volumes/pictrs to 991:991 manually"
docker compose up -d
echo "waiting for lemmy setup..."
for i in $(seq 60); do docker compose exec -T postgres psql -U lemmy -tAc "select site_setup from local_site" 2>/dev/null | grep -q t && break; sleep 5; done
docker compose exec -T postgres psql -U lemmy -c "update local_site set private_instance=true, federation_enabled=false, registration_mode='Closed'"
docker compose restart lemmy
echo "Lemmy up at http://${LEMMY_HOST}"
