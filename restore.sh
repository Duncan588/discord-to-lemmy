#!/bin/bash
# Optional: restore the dashboard SQLite DB from a restic repo (e.g. Cloudflare R2) whose
# snapshot contains an sqlite3 ".dump" stored via --stdin-filename.
set -euo pipefail; cd "$(dirname "$0")"
set -a; . ./.env; set +a
mkdir -p data bin
R=$(command -v restic || true)
if [ -z "$R" ]; then
  curl -sL https://github.com/restic/restic/releases/download/v0.17.3/restic_0.17.3_linux_amd64.bz2 | bunzip2 > bin/restic
  chmod +x bin/restic; R=./bin/restic; fi
SNAP=${RESTIC_SNAPSHOT:-latest}
echo "restoring $RESTIC_SQL_PATH from snapshot $SNAP"
rm -f "$SOURCE_DB"
( echo "PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;"; $R dump --path "$RESTIC_SQL_PATH" "$SNAP" "$RESTIC_SQL_PATH" ) \
  | docker run --rm -i -v "$PWD/data:/d" alpine sh -c "apk add -q sqlite >/dev/null && sqlite3 /d/$(basename "$SOURCE_DB")"
if [ -n "${RESTIC_PORTAL_PATH:-}" ]; then $R dump "${RESTIC_PORTAL_SNAPSHOT:-latest}" "$RESTIC_PORTAL_PATH" > "$PORTAL_DB"; fi
ls -la data
