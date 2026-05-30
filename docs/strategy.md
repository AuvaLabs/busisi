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

## Orchestration roadmap (deferred — re-evaluate Q3 2026)

Captured 2026-05-07 during the rewriter rollout. Decision deferred; do not
adopt until the trigger criteria below are met. The current systemd + cron +
Python scripts setup is sufficient for V1+V2 size.

### Tools considered

| Tool | License | Strength | Fit for grimoire |
|---|---|---|---|
| **Prefect** (core) | Apache 2.0 | Pythonic workflow orchestration; concurrency pools; UI dashboard; retries | **Strong** — replaces cron+systemd with observability + concurrency-aware scheduling. Same Python codebase, no rewrite. |
| **ControlFlow** (Prefect agent layer) | Apache 2.0 | Agent runtime built on Prefect; every agent step is a traceable task | **Latent** — relevant when grimoire wants autonomous editorial judgment (triage, source qualification, failure recovery). Not yet. |
| **N8N** | Sustainable Use License | Visual workflow editor; 500+ SaaS connectors; non-developer authoring | **Niche** — wins for SaaS glue (Stripe → Notion → Slack); awkward for our compute-heavy core pipeline. |

### Why this matters

The 2026-05-07 first-rewrite attempt hit a Featherless 429 because the hourly
cron `run_pipeline.sh` was already consuming the 4 concurrency units. Prefect's
**concurrency limits** (named pools tagged on tasks) would have queued the
interactive rewrite behind the cron tick instead of failing it. That's the
single most concrete "structural fix" Prefect would land — observability is
the second.

### Adoption path (when triggered)

| Phase | Scope | Trigger | Effort |
|---|---|---|---|
| **P1** | Wrap `run_pipeline.sh` as a Prefect flow that calls existing `python -m engine.core.X` commands. Add Prefect Server in Docker on the VPS. | First time we want failure alerts + a run-history dashboard | 1 day |
| **P2** | Convert rewriter pipeline to native Prefect tasks with `featherless` concurrency tag (limit=4) | First time Featherless 429 contention happens at non-trivial scale (probably as soon as cron starts running `--rewrite` daily) | 2 days |
| **P3** | Add daily `citation_intelligence` flow + Slack/email reporting | When we want passive ops visibility | 0.5 day |
| **P4** | ControlFlow editorial-triage agent | When validators-only logic stops cleanly expressing what we want | 3-5 days |

### Trigger criteria (status updated 2026-05-07)

- ❌ V3 vertical launches (not yet)
- ✅ **Featherless 429 contention happens >2× per week** — fired same-day on
  the first rewrite attempt; the concurrency-doc citation above confirms
  this is the platform's designed behavior, not transient. P1 promoted.
- ❌ Operator wants daily/weekly automated reports (manual CLI sufficient
  for now)
- ❌ Partner-webhook ingest (no partner asks yet)

One trigger fired → **P1 scheduled this sprint**. P2-P4 stay deferred.

### Why N8N is NOT recommended for the core pipeline

The core rewriter (Pass 0/1/2 + validators) is code-shaped, not workflow-shaped.
Putting it in N8N means either (a) a single "exec python" node — cosmetic, or
(b) re-implementing validators in N8N expressions — strictly worse than the
current 279-test Python. N8N's right scope is **partner webhook routing** when
that surface exists (Stripe, Cloudflare PPC events, sponsor inquiries).

### Decision marker

If we pick Prefect, ControlFlow comes free in the same install — adopting
Prefect doesn't lock out the agent layer. Pure-Python alternatives if Prefect
ever feels too heavy: **Dagster** (more opinionated, asset-graph-shaped) or
just keep cron + add `ops/notify.sh` for failure alerts (~50 lines).

## Rewriter zero-write incident (2026-05-30)

Pipeline ticks were writing **0 narratives** — every candidate rejected on
"narrative cites numbers not in source bodies". Diagnosis (replaying the
validator against production stories) found two root causes, both fixed +
deployed:

1. **Truncated validation pool** (commit 394d755). The numeric-grounding
   validator built its source pool from the member `body` field, truncated to
   3000 chars for use as a *tone reference*. Full articles run 12–15k chars, so
   any figure past char 3000 was invisible and falsely rejected as
   hallucinated — ~85% of rejections were this false positive. Fix: validate
   against an untruncated `full_body`; tone slice stays 3000. Regression test
   asserts a number past char 3000 validates.

2. **Single-key 429 = instant failure** (commit 53935da). The client rotated
   keys on 429/5xx but with one configured key (`keys=1`) had nothing to rotate
   to, so `attempts=1` → transient 429 became a hard drop. Logs showed ~7.6k
   429s + ~4.3k 504s over history. Fix: bounded retry-with-backoff (capped
   exponential + jitter, honors Retry-After up to `LLM_BACKOFF_CAP`) around the
   key-rotation pass. Env knobs: `LLM_MAX_RETRIES=3`, `LLM_BACKOFF_BASE=2.0`,
   `LLM_BACKOFF_CAP=30`.

This is the Prefect-P2 concurrency trigger firing in practice — but the
in-process backoff defers Prefect: revisit P2 only if write-rate stays
inadequate after these land, or once a 2nd Featherless key is provisioned
(rotation infra already exists; just append to `LLM_API_KEYS`).

**Open follow-ups:** (a) provision a 2nd Featherless key for true throughput;
(b) confirm next cron tick writes > 0 narratives.

## Last updated

2026-05-30 — rewriter zero-write fixed (full-body numeric validation +
single-key 429 backoff); both deployed (HEAD 53935da). 295 tests green.
