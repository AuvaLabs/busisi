#!/usr/bin/env bash
# grimoire backup — local Postgres dump + Cloudflare R2 push.
# Local dumps are short-retention (14 ticks); R2 holds the long tail.
# R2 push activates when AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY are
# exported (typically from /srv/grimoire/.env on VPS); otherwise the
# step is skipped and the local dump is still produced.
# See ops/runbooks/backup.md.
set -uo pipefail
LOG=/var/log/grimoire/backup.log
mkdir -p /var/log/grimoire
exec >>"$LOG" 2>&1
echo "[$(date -Iseconds)] backup start"

# Source env so the R2 leg sees credentials configured operator-side.
if [ -f /srv/grimoire/.env ]; then
  set -a
  # shellcheck disable=SC1091
  . /srv/grimoire/.env
  set +a
fi

DUMP_DIR=/srv/grimoire/backups/postgres
mkdir -p "$DUMP_DIR"
DATE=$(date +%Y%m%d-%H%M%S)
DUMP_PATH="$DUMP_DIR/dumpall-$DATE.sql.gz"
cd /srv/grimoire
if ! docker compose exec -T postgres pg_dumpall -U grimoire | gzip -9 > "$DUMP_PATH"; then
  echo "[$(date -Iseconds)] postgres dump FAILED"
  exit 1
fi
SIZE=$(du -h "$DUMP_PATH" | awk '{print $1}')
echo "[$(date -Iseconds)] postgres dump: $SIZE"

# Local retention: keep last 14 dumps; the R2 leg holds the long tail.
ls -1t "$DUMP_DIR"/dumpall-*.sql.gz | tail -n +15 | xargs -r rm --

# ---- R2 leg ----
# Cloudflare R2 is S3-compatible. Bucket grimoire-backups is provisioned;
# operator must export AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY scoped
# to that bucket only. Override R2_ENDPOINT/R2_BUCKET via env to point
# at a different account/bucket.
R2_ENDPOINT="${R2_ENDPOINT:-https://22fe4279ad540a78456e6e4c82e62a1f.r2.cloudflarestorage.com}"
R2_BUCKET="${R2_BUCKET:-grimoire-backups}"

if [ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "${AWS_SECRET_ACCESS_KEY:-}" ]; then
  if command -v aws >/dev/null 2>&1; then
    if aws --endpoint-url "$R2_ENDPOINT" s3 cp \
         "$DUMP_PATH" "s3://$R2_BUCKET/postgres/dumpall-$DATE.sql.gz" \
         --only-show-errors; then
      echo "[$(date -Iseconds)] R2 push ok ($R2_BUCKET/postgres/dumpall-$DATE.sql.gz)"
    else
      echo "[$(date -Iseconds)] R2 push FAILED (continuing — local dump is intact)"
    fi
  else
    echo "[$(date -Iseconds)] R2 push SKIPPED (aws CLI not installed)"
  fi
else
  echo "[$(date -Iseconds)] R2 push SKIPPED (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set)"
fi

echo "[$(date -Iseconds)] backup done"
