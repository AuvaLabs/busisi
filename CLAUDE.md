# Grimoire — Command Center

This file is the entry point for any agent or operator working on the
Grimoire platform. Read it before doing anything else.

**Two roles, one rule:**
- `deploy@sqx-automation` (this command center) is for design, plan, code, ops orchestration. All Tier-A creds live here in `~/kb_center/server_credentials.md`.
- `grimoire-auvalabs-01` (production VPS, SSH alias `grimoire`) is for serving the product. No Tier-A creds. No interactive editing — pull from GitHub.

## Live properties

| # | Brand | Domain | Topic | Status |
|---|---|---|---|---|
| V1 | **The Embedding Report** | `embedding.report` (canonical) + `embeddings.report` (301 → canonical) | AI/ML | Live, indexed, monetized via /advertise |
| V2 | **Vested** | `vested.news` | Personal finance for tech workers | Live, same |

Operating entity: **Auva Labs FZE**. All branded surfaces show this on `/privacy` + `/terms` only — never in the editorial voice.

## Core facts

- **GitHub:** https://github.com/AuvaLabs/grimoire (private, AuvaLabs org)
- **VPS:** `178.104.214.16` (Hetzner CPX 32, Falkenstein, Ubuntu 24.04). SSH alias `grimoire`, port 2222, key-only.
- **Postgres:** Docker compose (internal Docker net), data on `/srv/grimoire/data/postgres/`
- **Redis:** Docker compose, same network
- **Caddy:** native install (not docker), config at `/srv/grimoire/caddy/Caddyfile`, log dir `/var/log/caddy/`
- **TLS:** Cloudflare Origin Certificate (15-year, valid until 2041) at `/etc/ssl/grimoire/origin.{crt,key}`. Renewal class eliminated.
- **CF:** orange-cloud (proxied) on all 3 zones; SSL mode `strict`; `always_use_https` on
- **CF zone IDs (public):** embedding.report=`5136ef93965db0d6426c68e072baeb5a`, embeddings.report=`0e6b97654a4961b97c9af08297700c88`, vested.news=`bc0f4e0e860a278b5db3692b86356120`
- **Author identity (commits):** `Nicholai Imbong <nicholai@auvalabs.com>` — never AI/Claude attribution

## Workflow

1. **Plan.** Update `docs/registry.md` (status, dates) and `docs/strategy.md` (kill criteria, roadmap) before starting non-trivial work.
2. **Develop on command center.** Edit files in `/home/deploy/grimoire/`, run pytest locally.
3. **Commit + push.** Standard format `<type>: <description>` — feat/fix/refactor/docs/test/chore/perf/ci. NO AI attribution anywhere.
4. **Deploy.** SSH to grimoire, `cd /srv/grimoire && git pull origin main`, run alembic if migrations changed, reload Caddy / restart handler if relevant.
5. **Verify.** From any external machine: `curl -I https://embedding.report` returns 200 with `cf-ray:`, `server: cloudflare`.

## Ops scripts

Live on grimoire VPS at `/srv/grimoire/ops/`:

```bash
ssh grimoire 'sudo /srv/grimoire/ops/run_pipeline.sh'      # one-shot pipeline tick
ssh grimoire 'sudo /srv/grimoire/ops/run_digest.sh'        # weekly digest + send
ssh grimoire 'sudo /srv/grimoire/ops/backup.sh'            # local Postgres dump + R2 push
ssh grimoire 'sudo journalctl -u caddy -f'                  # Caddy logs
ssh grimoire 'sudo journalctl -u grimoire-handler -f'       # FastAPI handler logs
```

## Quality harness

`/srv/grimoire/ops/harness/audit.py` — per-page rubric scorer. Runs against the rendered output, scores meta/seo/aeo/geo/a11y/perf/privacy/monetization. Threshold: portfolio ≥ 87, page ≥ 85.

```bash
ssh grimoire 'PYTHONPATH=/srv/grimoire python3 /srv/grimoire/ops/harness/audit.py'
```

## Remote server layout

```
/srv/grimoire/
├── engine/
│   ├── core/                ← pipeline, curator, researcher, summarizer, output_renderer
│   ├── handlers/            ← FastAPI: subscribers, sponsors, tools, api_v1, affiliates, feedback
│   ├── shared/templates/    ← Jinja for all rendered surfaces
│   └── tests/
├── verticals/
│   ├── embedding/           ← V1 config + sources + partners
│   ├── vested/              ← V2 config + sources + partners
│   └── _template/           ← scaffold for V3+
├── ops/
│   ├── run_pipeline.sh      ← cron driver
│   ├── run_digest.sh        ← weekly digest
│   ├── backup.sh            ← R2 backup
│   ├── heartbeat.sh         ← Uptime Kuma push
│   ├── migrations/          ← alembic
│   ├── harness/             ← audit.py
│   └── runbooks/
├── caddy/Caddyfile
└── data/                    ← gitignored: postgres/ output/ snapshots/ backups/
```

## Monetization stack (current)

- **Affiliate redirect surface:** `/r/<partner>/<slug>` via `engine/handlers/affiliates.py`
- **Sponsor inquiry:** `/api/sponsor` + `/advertise` rate card page
- **AI-citation infrastructure:** `/llms.txt`, `/llms-full.txt`, `/feed.json`, `/.well-known/rsl.json`, `/.well-known/security.txt`, `/licensing`
- **Reader feedback:** `/api/feedback` writes to `article_feedback` table
- **Bot-hits telemetry:** Caddy log → `bot_hits` table via `engine/core/bot_log_parser.py`
- **AdSense pub ID:** Auva Labs operator account `pub-6400196438142777` (currently used on Atelier; reusable here once content quality justifies)
- **Partnerize Wise tag:** `158cbb21-2e35-4717-b88f-7101c4679a52` (operator's existing; usable on Vested for the finance audience)

## Domain-commit env (production)

In `/srv/grimoire/.env` on VPS:

```
EMBEDDING_CANONICAL_BASE=https://embedding.report
VESTED_CANONICAL_BASE=https://vested.news
```

Read at runtime by `engine.core.config.canonical_base_for(vertical_name)`.

## Pointers

- README: `/home/deploy/grimoire/README.md` (rendered on the GitHub repo page)
- Build directive: `docs/BUILD-DIRECTIVE.md` (historical strategic intent)
- Build complete handoff: `docs/build-complete.md` (capture + addendum)
- Launch checklist: `docs/launch-checklist.md`
- Architecture: `docs/architecture-derivation.md`
- Design: `docs/design-derivation.md`
- Security posture: `docs/security-posture.md`
- Backup runbook: `ops/runbooks/backup.md`
- SEO/AEO/GEO runbook: `ops/runbooks/seo-aeo.md` (IndexNow + GSC + CF Web Analytics)
- kb_center pointer: `~/kb_center/auvalabs_project.md` § Grimoire (command-center side)

## Last updated

2026-05-06 — Phase 24 monetization foundation + V1 rebrand + CF orange-cloud + Origin Cert. 22+ commits this session pushed.
