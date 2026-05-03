#!/usr/bin/env bash
# Weekly digest driver — render the archive page + send to confirmed
# subscribers for the previous full ISO week. Idempotent at the row level
# so a re-run (operator manual trigger, cron retry) won't double-deliver.
set -uo pipefail
LOG=/var/log/grimoire/digest.log
mkdir -p /var/log/grimoire
exec >> "$LOG" 2>&1

VERTICALS=("$@")
if [ ${#VERTICALS[@]} -eq 0 ]; then
  VERTICALS=(modelwatch vested)
fi

cd /srv/grimoire
source .venv/bin/activate
set -a; source .env; set +a

for V in "${VERTICALS[@]}"; do
  echo "[$(date -Iseconds)] digest start vertical=$V"
  PYTHONPATH=. python -m engine.core.newsletter_generator "$V" \
      --week-offset -1 --render-archive --send --log-level INFO || \
    echo "[$(date -Iseconds)] digest FAILED vertical=$V (continuing)"
  echo "[$(date -Iseconds)] digest done  vertical=$V"
done
