#!/usr/bin/env bash
# grimoire backup — local Postgres dump.
# R2 leg runs from the command center; see ops/runbooks/backup.md.
set -euo pipefail
LOG=/var/log/grimoire/backup.log
exec >>"$LOG" 2>&1
echo "[$(date -Iseconds)] backup start"

DUMP_DIR=/srv/grimoire/backups/postgres
mkdir -p "$DUMP_DIR"
DATE=$(date +%Y%m%d-%H%M%S)
cd /srv/grimoire
docker compose exec -T postgres pg_dumpall -U grimoire | gzip -9 > "$DUMP_DIR/dumpall-$DATE.sql.gz"
SIZE=$(du -h "$DUMP_DIR/dumpall-$DATE.sql.gz" | awk '{print $1}')
echo "[$(date -Iseconds)] postgres dump: $SIZE"

# Retention: keep last 14 dumps locally; longer retention belongs to R2 restic.
ls -1t "$DUMP_DIR"/dumpall-*.sql.gz | tail -n +15 | xargs -r rm --

echo "[$(date -Iseconds)] backup done (R2 leg pending operator R2 setup)"
