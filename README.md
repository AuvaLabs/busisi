# Grimoire

Multi-vertical knowledge platform. Ships Modelwatch (AI/ML) first, then
Vested (personal finance for tech workers), with N additional verticals
as configuration.

See `docs/BUILD-DIRECTIVE.md` for the complete v2 build directive.

## Layout

| Path | Purpose |
|---|---|
| `docs/`              | Architecture, design, runbook, security, monetization, editorial |
| `platform/core/`     | Vertical-agnostic engine (feed loader/fetcher, dedup, classifier, LLM client, renderer, ...) |
| `platform/shared/`   | Design tokens, base templates, shared CSS/JS |
| `platform/tests/`    | Unit + integration tests |
| `verticals/<name>/`  | Per-vertical sources.yaml, config.yaml, prompts/, content overrides |
| `ops/`               | Harness, runbooks, backup + deploy scripts |
| `caddy/`             | Caddyfile + per-site configs + sentinel placeholder pages |

## Operating

- **Server:** `grimoire-auvalabs-01` (Hetzner Cloud CPX 32, Falkenstein, Ubuntu 24.04 LTS).
- **SSH:** alias `grimoire` from the command center (deploy@VPS:2222, key-only).
- **Shared infra:** Postgres 16 + Redis 7 + Caddy 2 (managed via systemd; data on `/srv/grimoire/data/`).
- **Backups:** restic to Cloudflare R2 `grimoire-backups` (Phase 1; see `ops/runbooks/backup.md`).
- **Monitoring:** push heartbeat to status.auvalabs.com (existing Uptime Kuma).

## License

Proprietary — Auva Labs FZE. Internal repo.
