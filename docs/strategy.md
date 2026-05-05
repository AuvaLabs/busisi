# Strategy — Grimoire

Adopted from Atelier's `strategy.md` pattern. This is the long-form
roadmap, kill criteria, and dependency map. Read this before starting
any major project. For static "what's live" facts, see `registry.md`.

## North star

Build a multi-vertical knowledge ecosystem under Auva Labs FZE that
monetizes via affiliates + ads + AI-citation revenue (no subscription
until ≥12-month organic readership growth proves the audience).

Each property is a **distinct publication** with its own brand voice;
the engine is shared, the editorial identities are not.

## Phase model

| Phase | Definition | Live? |
|---|---|---|
| **Phase 1: Platform foundations** | Engine, DB, pipeline, single-vertical render. Postgres + Redis + Caddy. | ✓ |
| **Phase 2: Multi-vertical proof** | V2 (Vested) launches on the same engine. "Verticals are configuration." | ✓ |
| **Phase 3: Editorial depth** | Curator + researcher + entity extraction + story clustering. | ✓ |
| **Phase 4: Monetization foundation** | /llms.txt, /feed.json, RSL, /licensing, /api/v1, bot_hits, affiliate redirect, /advertise rate card. | ✓ |
| **Phase 5: V1 brand commit** | Real domains: embedding.report + vested.news + embeddings.report. CF orange-cloud + Origin Cert. | ✓ |
| **Phase 6: Distribution & growth** | GSC + Bing Webmaster submission, IndexNow integration, CF Web Analytics, glossary/learn surfaces, original-synthesis pieces. | In progress |
| **Phase 7: AI-citation revenue** | Apply Perplexity Publisher / TollBit / Cloudflare Pay-Per-Crawl after ≥30 days of bot_hits data. | Gated |
| **Phase 8: Ad revenue** | AdSense or Carbon Ads / EthicalAds when traffic crosses applicable thresholds. | Gated |
| **Phase 9: Premium tier** | Revisit subscription model only after 12 months of organic growth proves the audience cares enough. | Deferred |

## Kill criteria (per Atelier pattern)

### Per vertical
Kill if **MAU < 1K at month 6** with no improving trend. "Improving" = monotonically positive month-over-month for the trailing 3 months.

### Portfolio
Re-evaluate the whole grimoire bet if **no vertical crosses 5K MAU by month 9**.

### Per monetization stream
Kill if 0 dollars at month 12 and no qualified pipeline (signed sponsor / pending program approval / first commission).

## Build dependencies

```
Phase 1 ──┬──→ Phase 2 ──→ Phase 3 ──→ Phase 4 ──→ Phase 5 (DONE)
          │
          └──→ Backups + monitoring (R2, Kuma) (DONE)

Phase 5 ──→ Phase 6 (now)
              │
              ├──→ GSC/BWT submission ──┐
              ├──→ IndexNow integration ──┤──→ 30 days clean traffic ──→ Phase 7 (Perplexity / TollBit)
              ├──→ CF Web Analytics ──┘
              └──→ Original synthesis pieces ──→ Phase 8 (AdSense ready)

Phase 6 + Phase 7 + Phase 8 in parallel ──→ 12 months audience growth ──→ Phase 9 (premium revisit)
```

## V3+ decision rules (when to add a vertical)

Don't add a third vertical until **at least one of V1, V2 has crossed 5K MAU**.
Reasons:
- Engine is built, but distribution isn't. Adding V3 triples the cold-start problem.
- Operator attention is the binding constraint, not code.
- Each property needs ~20-30 hours/week of editorial attention to feel alive.

When the gate is passed, V3 candidates (in order of topical fit):
1. **Energy / compute economics** — direct overlap with AI infra (V1) + capex/cost analysis (V2)
2. **Devtools / engineering practices** — audience overlap with V1
3. **Policy / regulation** — cross-pollinates V1 + V2
4. **Audit / accountability / security (consolidated tech)** — broad

## Roadmap (next 4 weeks)

| Week | Deliverable |
|---|---|
| 1 | GSC + BWT submission + sitemap submitted; CF Web Analytics enabled; IndexNow integration shipped + auto-pinging |
| 2 | First original-synthesis piece per vertical (long-form, ≥1500 words, ≥10 cited sources) |
| 3 | Glossary skeleton (`/glossary/` index + 5-10 seed entries per vertical) — gated on rewriter (Phase 22f) |
| 4 | Quality harness (`audit.py`) re-run with portfolio score ≥ 87 confirmed; Phase 22f rewriter merge if grounding rule decided |

## Editorial conventions (per atelier pattern)

- **Standard commit format:** `<type>: <description>` — feat/fix/refactor/docs/test/chore/perf/ci. NO Claude / AI / agent attribution anywhere.
- **Author identity:** every commit + tag is `Nicholai Imbong <nicholai@auvalabs.com>`.
- **Three-copy workflow:** does NOT apply (we use command-center → GitHub → VPS pull).
- **Editorial integrity:** sponsored content labeled "Sponsored" on every surface; affiliate links carry `rel="sponsored"` + footnote disclosure.
- **No fake bylines:** Schema.org `Person` reserved for upstream-journalist attribution from extracted source data, never invented. Use `author: Organization` on NewsArticle markup.
- **No backlink sales:** Google manual-action class. Stated explicitly on `/advertise`.

## Cross-project policies

- **Tier-A creds:** live ONLY on the command center at `~/kb_center/server_credentials.md`. Never on grimoire VPS, never in GitHub, never in `.env` examples.
- **Tier-B creds:** mode 600 `.env` on the VPS only when it materially improves operations.
- **Pre-commit secret scanning:** future addition (atelier pattern — `secret-scan.sh`).
- **Backup:** `ops/backup.sh` does pg_dumpall → 14-day local rolling → R2 grimoire-backups via aws CLI.

## Last updated

2026-05-06 — Phase 5 complete; Phase 6 in progress (Tier-0 SEO submissions + IndexNow integration shipping next).
