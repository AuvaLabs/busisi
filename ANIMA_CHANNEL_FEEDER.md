# Vested → Anima channel feeder — KICKOFF

Goal: make **vested.news** a structured **story source** for the Anima finance channel
**OFF THE BOOKS** (`/home/deploy/auvalabs/anima/finance`). Anima already has a `story_engine`
(NEED/DEMAND/RARITY scorer) + a `fact_gate` that verifies every on-screen number against a PRIMARY
source. Vested gives it timely topics + the primary-source links to fact-check them. Each episode
links back to vested ("see the receipts"); vested links to the episode. Flywheel.

This is a SEPARATE session/repo (grimoire). The Anima session stays on finance. Coordinate via the
JSON contract in §3.

## GUARDRAILS (vested.news is LIVE / production)
1. Work on a **branch** (`feature/anima-feeder`), not straight on main. Open a PR.
2. **Additive only** — add sources + API fields/endpoint. Do NOT remove or rename existing feed/API
   fields (other consumers + the live site depend on them).
3. **Do NOT touch the `embedding` vertical.** This is the `vested` vertical only.
4. Run `engine/tests/` before/after; don't break the site or the existing RSS/JSON feed.
5. No secrets inline — API keys for new data sources go in env/config the existing way.

## What to build (grounded in the current code)
You already have: `verticals/vested/sources.yaml`, `engine/core/{feed_loader,feed_fetcher,source_health}.py`,
`engine/handlers/api_v1.py`, `engine/shared/templates/{feed.rss.xml,feed.json}`.

1. **Add primary-source data feeds** to `verticals/vested/sources.yaml` (not just news outlets):
   FRED (St. Louis Fed), BLS, BEA, Treasury Fiscal Data, SSA, CBO, IRS SOI, SEC/EDGAR, CFPB — these
   carry the actual NUMBERS + authoritative source. Plus consumer-finance outlets: NerdWallet (have),
   Investopedia, Bankrate, Morningstar, Kiplinger; research: SPIVA (S&P), ICI, Vanguard/Fidelity,
   PGPF, Tax Policy Center, Pew. Weight US + consumer-impact (the channel is US personal finance).
2. **Per-story enrichment** (extend the classifier/indexer): extract and store
   - `key_stat` — the central number in the story (e.g. "$1.66T", "23%", "2033")
   - `primary_source_url` — the authoritative link behind that stat (follow through the outlet)
   - `lane` — one of: "What It Really Costs" | "The Cost of Waiting" | "Where Your Money Goes" | "Money, Explained"
   - `evergreen` — bool: is this an evergreen-explainer topic vs one-off news
   - `momentum` — a simple trend signal (story velocity / cross-source cluster size; Google Trends or
     Reddit optional later) = the channel scorer's DEMAND axis
3. **Economic-release calendar** — a small source/feature listing scheduled drops (CPI, FOMC, jobs,
   SS Trustees report) with dates, so the channel can pre-plan timely episodes. Expose via the API.
4. **Structured JSON API for Anima** — extend `api_v1` (or add `/api/v1/anima/feed`) and `feed.json`
   to emit the contract in §3. RSS stays as-is for the site.

## 3. The JSON contract (what Anima's `vested_source.py` will consume)
Stable shape; additive changes only. One array of recent stories:
```json
{
  "generated_at": "ISO-8601",
  "vertical": "vested",
  "stories": [
    {
      "id": "stable-id",
      "headline": "string",
      "summary": "string",
      "url": "outlet article url",
      "source": "BBC | Fed | NerdWallet | FRED | ...",
      "primary_source_url": "authoritative link behind the key stat (nullable)",
      "key_stat": "string e.g. $1.66T (nullable)",
      "entities": ["Federal Reserve", "Social Security", "..."],
      "lane": "What It Really Costs | The Cost of Waiting | Where Your Money Goes | Money, Explained | null",
      "evergreen": true,
      "published_at": "ISO-8601",
      "momentum": 0.0
    }
  ]
}
```
Anima scores these on NEED/DEMAND/RARITY + a TIMELINESS axis (recency × momentum), drafts the script,
and fact-gates each number against `primary_source_url`. So `key_stat` + `primary_source_url` are the
highest-value fields — they drop straight into Anima's `claims.json`.

## Definition of done
A branch/PR that: adds the primary-data + consumer-finance sources; enriches stories with
key_stat / primary_source_url / lane / evergreen / momentum; exposes the §3 JSON contract via the API
(+ optional calendar endpoint); passes `engine/tests/`; does not change existing feed/RSS fields or the
embedding vertical; the live site still works.

See `/home/deploy/auvalabs/anima/PLATFORM.md` for how Anima (the production side) is structured —
grimoire (sourcing) and anima (production) are the two halves of the portfolio.
