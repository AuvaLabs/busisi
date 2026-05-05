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
  VERTICALS=(embedding vested)
fi

cd /srv/grimoire
source .venv/bin/activate
set -a; source .env; set +a

for V in "${VERTICALS[@]}"; do
  echo "[$(date -Iseconds)] pipeline start vertical=$V"
  PYTHONPATH=. python -m engine.core.pipeline "$V" --persist --scrape --enrich --enrich-max 20 --log-level WARNING || \
    echo "[$(date -Iseconds)] pipeline FAILED vertical=$V (continuing)"
  # Extract named entities. --max 10 caps per-tick LLM cost; backfill of
  # the historical corpus drains organically. Idempotent via
  # Article.entities_extracted_at.
  PYTHONPATH=. python -m engine.core.entity_extractor "$V" --max 10 --sleep 1 --log-level WARNING || \
    echo "[$(date -Iseconds)] entities FAILED vertical=$V (continuing)"
  # Curator scores every article whose curator_version < CURATOR_VERSION
  # (rule-based, free). Runs AFTER entity extraction so the
  # entity_strength signal sees fresh entity counts.
  PYTHONPATH=. python -m engine.core.curator "$V" --max 500 --log-level WARNING || \
    echo "[$(date -Iseconds)] curator FAILED vertical=$V (continuing)"
  # LLM-judge for gray-zone (curator_tier=researcher) articles. Cap per
  # tick keeps cost bounded; backfill drains across cron ticks. Skips
  # rows where curator_signals.judge is already set (idempotent).
  PYTHONPATH=. python -m engine.core.curator_judge "$V" --max 30 --log-level WARNING || \
    echo "[$(date -Iseconds)] curator_judge FAILED vertical=$V (continuing)"
  # Researcher fetches supporting docs for tier=researcher articles
  # whose researched_at IS NULL. Capped per tick to keep web-API
  # spend predictable.
  PYTHONPATH=. python -m engine.core.researcher "$V" --log-level WARNING || \
    echo "[$(date -Iseconds)] researcher FAILED vertical=$V (continuing)"
  # Cluster fresh articles into multi-source Story rows BEFORE rendering so
  # the front page picks up new clusters this tick. Idempotent — articles
  # already linked to a Story are skipped.
  PYTHONPATH=. python -m engine.core.story_clusterer "$V" --days 7 --log-level WARNING || \
    echo "[$(date -Iseconds)] cluster FAILED vertical=$V (continuing)"
  PYTHONPATH=. python -m engine.core.output_renderer "$V" --log-level WARNING || \
    echo "[$(date -Iseconds)] render FAILED vertical=$V (continuing)"
  # Caddy access-log → bot_hits. Idempotent (skips lines older than the
  # most-recent recorded ts). Ignored if the log file is absent — the
  # parser warns and returns 0.
  PYTHONPATH=. python -m engine.core.bot_log_parser "$V" --log-level WARNING || \
    echo "[$(date -Iseconds)] bot_log_parser FAILED vertical=$V (continuing)"
  # IndexNow push to Bing/Yandex — tells them about the day's new URLs
  # so push-mode indexing kicks in within minutes vs the hours/days
  # crawl-mode discovery would take. Fail-open.
  PYTHONPATH=. python -m engine.core.indexnow "$V" --log-level WARNING || \
    echo "[$(date -Iseconds)] indexnow FAILED vertical=$V (continuing)"
  echo "[$(date -Iseconds)] pipeline done vertical=$V"
done
