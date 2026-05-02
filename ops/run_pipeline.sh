#!/usr/bin/env bash
# Grimoire pipeline + render driver. One vertical per invocation.
set -euo pipefail
VERTICAL=${1:-modelwatch}
LOG=/var/log/grimoire/pipeline.log
mkdir -p /var/log/grimoire
exec >> "$LOG" 2>&1
echo "[$(date -Iseconds)] pipeline start vertical=$VERTICAL"
cd /srv/grimoire
source .venv/bin/activate
set -a; source .env; set +a
PYTHONPATH=. python -m engine.core.pipeline "$VERTICAL" --persist --scrape --log-level WARNING
PYTHONPATH=. python -m engine.core.output_renderer "$VERTICAL" --log-level WARNING
echo "[$(date -Iseconds)] pipeline done"
