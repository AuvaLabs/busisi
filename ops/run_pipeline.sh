#!/usr/bin/env bash
# Grimoire pipeline + render driver. Runs the full chain for one or more
# verticals: feed_loader -> feed_fetcher -> dedup -> classifier -> persist
# -> render. Each vertical's failures are isolated so one stuck source
# cannot block the others.
set -uo pipefail
LOG=/var/log/grimoire/pipeline.log
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
  echo "[$(date -Iseconds)] pipeline start vertical=$V"
  PYTHONPATH=. python -m engine.core.pipeline "$V" --persist --scrape --log-level WARNING || \
    echo "[$(date -Iseconds)] pipeline FAILED vertical=$V (continuing)"
  PYTHONPATH=. python -m engine.core.output_renderer "$V" --log-level WARNING || \
    echo "[$(date -Iseconds)] render FAILED vertical=$V (continuing)"
  echo "[$(date -Iseconds)] pipeline done vertical=$V"
done
