# Build complete — Grimoire handoff

**Captured:** 2026-05-02 (initial); republished 2026-05-03 with the GitHub mirror live.
**Build state:** Phases 0–7 shipped; Phase 8 finishing items pending operator-supplied credentials.
**Handoff to:** the operator (`nicholai@auvalabs.com`) and any future agent resuming the build.

## Repository

- **GitHub:** https://github.com/AuvaLabs/grimoire (private, AuvaLabs org)
- **VPS source-of-truth:** `/srv/grimoire/` on `grimoire-auvalabs-01`. Auto-pushes every commit to GitHub via a per-repo deploy SSH key (`.git/hooks/post-commit`).
- **Command center mirror:** `/home/deploy/grimoire/` on `deploy@sqx-automation`. HTTPS push via `gh` CLI (existing AuvaLabs auth).
- **Author identity:** every commit + tag is `Nicholai Imbong <nicholai@auvalabs.com>`. No AI/agent attribution in commits, README, contributors, or changelogs — internal policy memorialised in the `reference_github_repo.md` project-memory entry.

---

## What was built

A multi-vertical knowledge platform serving two tenants — **Modelwatch**
(AI/ML) and **Vested** (personal finance for tech workers) — on a single
engine, single VPS. The engine is vertical-agnostic; adding a third tenant
is a configuration job.

**Live URLs (placeholder hostnames until DNS commits):**

- `http://178.104.214.16/` — Modelwatch front (or via `Host: modelwatch.local`)
- via `Host: vested.local` — Vested front
- All canonical paths live for both: `/`, `/about`, `/methodology`, `/privacy`, `/terms`, `/sources`, `/tools/`, `/llms.txt`, `/robots.txt`, `/sitemap.xml`

**Implemented platform/core modules (15 substantive + 3 stubbed):**

| Implemented | Pending Synthesize API |
|---|---|
| `config` | `summarizer` |
| `safe_http` (SSRF guard) | `entity_extractor` |
| `llm_client` (multi-key + circuit breaker) | `story_clusterer` |
| `llm_cache` (Redis-backed) | `reference_writer` |
| `llm_usage` (per-key/day/vertical) | `research_writer` |
| `feed_loader` | `newsletter_generator` |
| `feed_fetcher` | `distribution_engine` |
| `deduplicator` (word-shingle + per-vertical guards) | |
| `classifier` (regex + LLM escalation) | |
| `article_scraper` (trafilatura) | |
| `source_health` | |
| `output_renderer` (Jinja2 + tokens) | |
| `tools_engine` (dynamic Python-defined tools) | |
| `pipeline` (orchestrator) | |
| `db` (SQLAlchemy 2.0 schema) | |

**Git timeline (16 commits, 16 tags):**

```
phase-1-foundation             hardened VPS, Docker, Postgres, Redis, Caddy
phase-2-foundation             engine/core 9-impl + 14-stub, 18 dedup tests
phase-3-modelwatch-config      48 modelwatch sources + 13-topic taxonomy
phase-3-pipeline-smoke         end-to-end first run (real OpenAI articles)
phase-3-postgres-schema        multi-tenant SQLAlchemy schema
phase-3-pipeline-persist       articles persisting to postgres
phase-3-modelwatch-live        rendered front page served via Caddy
phase-3-pipeline-cron          auto-refresh every 10 min
phase-3-static-pages           /about /methodology /privacy /terms /sources
phase-3-article-bodies         trafilatura body scrape wired in
phase-3-seo-meta               /llms.txt /robots.txt /sitemap.xml
phase-4-monetization-schema    subscribers + pro_users + sponsor_inquiries tables
phase-3-tools                  /tools/ + LLM cost calculator
phase-5-vested-scaffold        second vertical live (multi-tenant proven)
phase-6-harness                quality scoring at 95.7% (threshold 87)
[phase 7]                      security-posture.md doc
[phase 8]                      launch-checklist + announcements + this doc
```

---

## What's measurably good

- **Quality harness:** 95.7 / 100 average across both verticals. Threshold 87. Six of ten dimensions auto-graded; four (content quality, source attribution, editorial integrity, accessibility) stubbed pending Synthesize API + axe-core.
- **Pipeline:** end-to-end working. Real OpenAI / Google AI / Bogleheads articles ingested, deduplicated, classified, body-scraped, persisted, rendered, served. Cron runs every 10 min for both verticals.
- **Multi-tenant:** Vested launched on the same engine as Modelwatch with zero engine changes — only `verticals/vested/{config.yaml,sources.yaml}` plus a Caddy site block plus a Postgres `Vertical` row. The directive's "verticals are configuration, not rebuilds" promise is verified.
- **Security:** UFW default-deny, SSH port 2222 key-only, `ssh.socket` disabled (Ubuntu 24.04 footgun documented), fail2ban, unattended-upgrades, SSRF guard installed at every process start, security headers global, Postgres + Redis on internal-only bridge, Tier-A creds never on the exposed server.
- **Resilience:** the pipeline handles per-feed 404/SSL/DNS failures gracefully (one bad source does not break the run); dedup state persists across runs; LLM client circuit-breaker caps blast radius of upstream outages.

---

## What's pending (gated on external dependencies)

| Blocker | Unblocks |
|---|---|
| **Synthesize / Groq API key** in `.env` | LLM-driven content modules (summariser, entity extractor, story clusterer, reference writer, research writer); LLM-graded harness dimensions; daily newsletter digest content; reference-layer 50+ glossary entries; research-layer "State of AI Q1 2026" piece. |
| **Postmark / Resend API token** in `.env` | Newsletter signup → confirmation → daily digest delivery end-to-end. |
| **Stripe account + secret + webhook secret** in `.env` | Pro tier signup → checkout → access granted end-to-end; sponsor inquiry billing path. |
| **Cloudflare R2 bucket + IP-allowlisted token** at `/home/deploy/.r2-grimoire.env` (command center) | Off-box backup leg; weekly restore drill. Currently only local Postgres dumps run nightly. |
| **Domain commit + DNS** | Real hostnames in Caddy + canonical URLs; auto-TLS via Cloudflare DNS-01; Cloudflare cache-HTML rule. Until then `<vertical>.local` placeholders + bare-IP routing serve the demo. |
| **FastAPI handler app** (engine work, not external) | `/api/subscribe`, `/api/sponsor`, `/auth/magic-link`, `/api/tools/<slug>/calculate` endpoints. Schema exists; handler is the next engine work-item once Synthesize API enables full content pipeline testing. |

**The build is at a clean handoff point.** Each pending item has its
landing zone prepared (env variables, schema, handler stubs, runbooks).
None of the pending items require redoing existing work.

---

## Operator first-review priorities

In order of leverage:

1. **Drop in the Synthesize API key.** Single-line change to `/srv/grimoire/.env`. Everything LLM-driven unlocks.
2. **Audit the disabled feed URLs.** 4 in `verticals/modelwatch/sources.yaml`, 8 in `verticals/vested/sources.yaml` — comment-marked `# DISABLED 2026-05-02`. Replace with current URLs as you find them.
3. **Review the privacy + terms drafts** at `/privacy` and `/terms` for both verticals (banner-marked DRAFT). Get them ratified by your legal counsel before public launch.
4. **Set up R2 bucket + token** per `ops/runbooks/backup.md`. Without this the nightly dump only lives on the box itself.
5. **Decide and commit the real domains.** This is the single biggest visibility gain — the moment the placeholder `.local` hostnames swap for real domains, indexing + backlinks begin.
6. **Add Stripe + Postmark accounts.** Once the FastAPI handler app lands, these two creds unlock the entire monetisation path.

---

## Recommended next-30-days operations cadence

**Daily (automated):**
- Cron pipeline ticks every 10 min for both verticals (in place).
- Backup runs at 03:30 UTC (in place).
- Quality harness runs at 04:30 UTC (in place).
- Heartbeat to Uptime Kuma every minute (env-gated).

**Weekly (operator):**
- Sunday morning: read the week's harness reports under `ops/harness/reports/`. If average score drops below 90, investigate.
- Tuesday morning: review the `sponsor_inquiries` table; respond within 48h.
- Wednesday: spot-check 20 random LLM summaries for grounding (once the LLM tier is live). Log violations as harness work-items.
- Friday: skim the `articles` table for the week to ensure source diversity (if 60% of stories come from one outlet, escalate the source-balance config).

**Monthly (operator):**
- First-of-month: source URL audit. Replace any 5xx/404/SSL failures from the last 30 days of `feed_health:*` Redis state.
- Mid-month: tax-rule freshness audit (Vested) — confirm IRS-quoted figures still match the current year's IRS publications.
- Last-of-month: Pro-tier churn analysis from `pro_users.status`. Net signup count, average tier mix, MRR.

**Quarterly:**
- Refresh the LLM cost calculator pricing table (`verticals/modelwatch/tools/llm_cost_calculator.py:_PRICING`).
- Refresh the `last_verified` date on every glossary entry; re-verify any that names a specific model capability or product feature.
- Source list review — add 2–3 new sources, retire 2–3 that aren't producing signal.
- Restore drill: pick one snapshot from R2, restore to scratch DB, verify integrity.

**Annually:**
- Rotate every Tier-A credential (Cloudflare Global Key, R2 keys, Stripe keys, Postmark token, LLM keys).
- Reread BUILD-DIRECTIVE alongside this `build-complete.md` to confirm the platform's still operating per the locked v2 spec.

---

## Adding a third vertical

Walking through the directive's termination criterion #12 ("vertical template tested — walk through 'add cybersecurity-extended vertical' mentally"):

1. Pick a name + accent colour. Update `design-derivation.md` with the new accent.
2. `cp -r verticals/_template/ verticals/cyberwatch/` (or whatever).
3. Fill `verticals/cyberwatch/sources.yaml` (40+ feeds across priority bands).
4. Fill `verticals/cyberwatch/config.yaml` with topics, entity types, dedup guards, escalation budget.
5. Optionally add `verticals/cyberwatch/tools/<tool>.py` modules.
6. Seed `Vertical` row in Postgres: `INSERT INTO verticals(name, display_name, accent_light, accent_dark) VALUES ('cyberwatch', 'CyberWatch', '#...', '#...');`.
7. Add Caddy site block (mirror modelwatch.local / vested.local).
8. Update `ops/run_pipeline.sh` default verticals list (or invoke the cron with explicit args).
9. Run pipeline once manually; render once; verify harness ≥ 87.
10. Tag `phase-N-<name>-scaffold`; commit.

The bound-by-config promise holds: zero engine changes for a third vertical.

---

## Honest limits of this build

- **No real LLM integration end-to-end yet.** The grounding rules, the
  classifier escalation logic, the cache wiring, the budget cap — all in
  place and unit-testable. But the actual round-trip through a live API
  is gated on the Synthesize key drop.
- **Reference layer is empty.** The directive specifies 50+ glossary
  entries per vertical; that volume of grounded content needs an LLM
  drafter + editorial review loop, both of which are gated.
- **Newsletter, Pro tier, sponsor inquiry forms are not yet interactive.**
  The schema is in place; the FastAPI handler is the next engine
  work-item.
- **Cross-source story clustering is not yet active.** `story_clusterer`
  is a stub. Implementing it is straightforward (dedup similarity +
  entity overlap + time proximity); doing it well requires the entity
  extractor (LLM-gated).

None of these are surprises; all are tracked above. The platform is
production-grade *for the implemented scope* and ready to absorb the
gated work as the dependencies arrive.
