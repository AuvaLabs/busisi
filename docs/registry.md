# Registry — single source of truth for Grimoire properties

Update this file on every status change. Adopted from Atelier's pattern
(`/srv/atelier/registry.md`) as the canonical answer to "what's live, what's
planned, who owns what."

## Verticals (live + planned)

| # | Brand | Domain | Topic | Status | Launched | Operator |
|---|---|---|---|---|---|---|
| V1 | **The Embedding Report** | `embedding.report` (canonical) | AI/ML news, research, tooling | Live | 2026-05-06 | nicholai@auvalabs.com |
| V1d | (defensive plural) | `embeddings.report` | n/a (301 redirect) | Live | 2026-05-06 | same |
| V2 | **Vested** | `vested.news` | Personal finance for tech workers | Live | 2026-05-06 | same |
| V3 | TBD | TBD | TBD | Planning | — | — |

## Operating entity

**Auva Labs FZE** — UAE-based publisher. Disclosed only on `/privacy` and
`/terms` per editorial policy. Never in headline / front-page / story
copy.

## Domain-status table

| Domain | Registrar | Proxied (CF) | A → IP | TLS source | Cert valid until |
|---|---|---|---|---|---|
| embedding.report | Cloudflare | orange-cloud | `178.104.214.16` | CF Origin Cert (multi-SAN) | 2041-05-01 |
| embeddings.report | Cloudflare | orange-cloud | `178.104.214.16` | CF Origin Cert (multi-SAN) | 2041-05-01 |
| vested.news | Cloudflare | orange-cloud | `178.104.214.16` | CF Origin Cert (multi-SAN) | 2041-05-01 |

CF zone IDs (public):
- embedding.report = `5136ef93965db0d6426c68e072baeb5a`
- embeddings.report = `0e6b97654a4961b97c9af08297700c88`
- vested.news = `bc0f4e0e860a278b5db3692b86356120`

CF SSL mode: `strict` on all 3. `always_use_https` on.

## Infrastructure summary

| Layer | Product | Location |
|---|---|---|
| Compute | Hetzner Cloud CPX 32 (Falkenstein, fsn1) | `grimoire-auvalabs-01`, IP 178.104.214.16 |
| OS | Ubuntu 24.04.3 LTS | — |
| Edge / TLS | Cloudflare orange-cloud | per-zone |
| Origin server | Caddy 2.11.x | systemd, port 80 + 443 |
| App tier | FastAPI handler | `/srv/grimoire/.venv/bin/uvicorn engine.handlers.app:app`, port 8001 |
| DB | Postgres 16 | Docker compose, internal net |
| Cache | Redis 7 | Docker compose, internal net |
| Backup leg 1 | local pg_dumpall | `/srv/grimoire/backups/postgres/` (14-day) |
| Backup leg 2 | Cloudflare R2 | bucket `grimoire-backups` (account `22fe4279...`) |
| Monitoring | Uptime Kuma push | `status.auvalabs.com` |

## API surface (live)

| Endpoint | Verb | Purpose |
|---|---|---|
| `/api/subscribe` | POST | Newsletter signup, double opt-in |
| `/confirm` | GET | Subscribe confirm token |
| `/unsubscribe` | GET | Unsubscribe token |
| `/api/sponsor` | POST | Sponsor / advertise inquiry |
| `/api/tools/<vertical>/<slug>/calculate` | POST | Calculator-style tool execution |
| `/api/v1/health` | GET | Liveness |
| `/api/v1/articles?vertical=&limit=&since=` | GET | Article list (skip-tier excluded) |
| `/api/v1/entities?vertical=&type=&limit=` | GET | Entity list |
| `/api/feedback` | POST | Reader-flag report |
| `/r/<partner>/<slug>` | GET | Affiliate redirect with UTM + click logging |

## Static surfaces (live)

| Path | Purpose |
|---|---|
| `/` | Front page (curated story cards) |
| `/story/<slug>/` | Individual story page with NewsArticle JSON-LD |
| `/sources` | Source directory + health |
| `/tools/` | Tool index per vertical |
| `/entity/` | Entity index |
| `/digest/` | Weekly newsletter archive |
| `/about`, `/methodology`, `/privacy`, `/terms`, `/licensing`, `/advertise` | Static editorial pages |
| `/llms.txt`, `/llms-full.txt` | AI-ingestion content index |
| `/feed.rss`, `/feed.json` | Syndication feeds |
| `/sitemap.xml`, `/robots.txt` | SEO surfaces |
| `/.well-known/rsl.json`, `/.well-known/security.txt` | Machine-readable manifests |

## Database tables (live, alembic chain)

| Migration | Tables / changes |
|---|---|
| 0001_baseline | verticals, articles, stories, story_articles, entities, article_entities, subscribers, pro_users, sponsor_inquiries, engagement_events |
| 0002_curator | articles += curator_score/tier/signals/version, researched_at; research_bundles; article_feedback |
| 0003_bot_hits_affiliate_clicks | bot_hits; affiliate_clicks |
| 0004_rebrand_modelwatch_embedding | UPDATE verticals SET name='embedding', display_name='The Embedding Report' WHERE name='modelwatch' |

## Monetization stack

| Stream | Status | Notes |
|---|---|---|
| Sponsorship inquiry | Live | `/api/sponsor` form on `/advertise` |
| Affiliate redirect | Live infra; placeholder codes | `partners.yaml` per vertical needs real `?ref=` codes |
| Newsletter sponsorship | Infra ready | Operator pricing TBD |
| AdSense | Application pending | Reuse pub `pub-6400196438142777` once content quality + traffic justify |
| Partnerize Wise (Vested) | Tag exists (operator's atelier account) | Tag `158cbb21-2e35-4717-b88f-7101c4679a52`; deploy on Vested when content has financial-product mentions |
| Perplexity Publisher Program | Not yet applied | Apply after ≥30 days of bot_hits data |
| TollBit / Cloudflare Pay-Per-Crawl | Not yet applied | Same gate |

## Last updated

2026-05-06 — V1 rebrand + CF orange-cloud + Origin Cert + alembic 0004 + 22 session-commits.
