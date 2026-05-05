# Grimoire

Multi-vertical knowledge platform. Ships Modelwatch (AI/ML) first, then
Vested (personal finance for tech workers), with N additional verticals
as configuration.

See `docs/BUILD-DIRECTIVE.md` for the complete v2 build directive.

## Layout

| Path | Purpose |
|---|---|
| `docs/`              | Architecture, design, runbook, security, monetization, editorial |
| `engine/core/`       | Vertical-agnostic engine (feed loader/fetcher, dedup, classifier, curator, researcher, LLM client, renderer, bot-log parser, ...) |
| `engine/handlers/`   | FastAPI mutating + read-API surface (subscribe / sponsor / tools / api_v1 / affiliates) |
| `engine/shared/templates/` | Jinja templates + design tokens |
| `engine/tests/`      | Unit + integration tests (186/186 green) |
| `verticals/<name>/`  | Per-vertical sources.yaml, config.yaml, partners.yaml |
| `ops/`               | Pipeline driver, backup, runbooks, alembic migrations |
| `caddy/`             | Caddyfile + per-site configs + sentinel placeholder pages |

## Operating

- **Server:** `grimoire-auvalabs-01` (Hetzner Cloud CPX 32, Falkenstein, Ubuntu 24.04 LTS).
- **SSH:** alias `grimoire` from the command center (deploy@VPS:2222, key-only).
- **Shared infra:** Postgres 16 + Redis 7 + Caddy 2 (Docker compose; data on `/srv/grimoire/data/`).
- **Backups:** `ops/backup.sh` does pg_dumpall → 14-day local rolling → Cloudflare R2 `grimoire-backups` via `aws s3 cp` (S3-compatible). Activates when `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` are exported. See `ops/runbooks/backup.md`.
- **Monitoring:** push heartbeat to status.auvalabs.com (existing Uptime Kuma).
- **Monetization (no premium):** four-lane strategy — AI-citation surface (RSL + llms-full + JSON Feed + structured data), affiliate redirect at `/r/<partner>/<slug>`, `/advertise` rate card, bot-hits telemetry. See `docs/launch-checklist.md` "Monetization + AI-citation surface".

## License

Proprietary — Auva Labs FZE. Internal repo.
