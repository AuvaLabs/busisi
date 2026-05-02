# Architecture Derivation — from ThreatWatch to Grimoire

**Captured:** 2026-05-02 from `auvalabs:~/threatwatch` at HEAD `fffecca`.
**Source repo:** github.com/AuvaLabs/threatwatch (private).
**Purpose:** distill the patterns Grimoire copies, the patterns it intentionally diverges from, and the explicit algorithms (word-shingle dedup, hybrid classifier escalation rules, LLM client rotation/circuit-breaker) that must be replicated faithfully.

---

## 1. ThreatWatch at a glance

Single-tenant cybersecurity-news aggregator. One pipeline, one output (the threatwatch.html dashboard + RSS). ~40 modules under a flat `modules/` package. Two containers: `pipeline` (cron-style scheduler running fetch → dedup → enrich → write every ~10 min) and `server` (read-only static HTML + small JSON API).

```
config/feeds_*.yaml        →  feed_loader.load_feeds_from_files()
                             ↓
                          feed_fetcher.fetch_articles()        ← ThreadPoolExecutor(MAX_FEED_FETCH_THREADS=16)
                             ↓                                   - feedparser per URL, retry on 429/5xx
                          deduplicator.deduplicate_articles()    - normalize URL, hash = SHA256(title + URL)
                             ↓                                   - persists hash + title state
                          article_scraper.process_urls_in_parallel()  ← trafilatura clean
                             ↓
                          hybrid_classifier.classify_article()   ← keyword first, AI escalation if low-conf
                             ↓
                          ai_enrichment.run_ai_enrichment()      ← four optional tiers, each guarded
                             ↓
                          output_writer.write_*()                ← hourly + daily JSON, RSS feed
```

Sequenced from `threatdigest_main.py`. SSRF guard installed at process start (`install_ssrf_guard`); LLM circuit breaker reset per run (`reset_circuit`).

---

## 2. Module structure

Flat `modules/` directory, one concern per file. The pipeline-relevant modules Grimoire derives from:

| ThreatWatch module | Role | Grimoire equivalent |
|---|---|---|
| `feed_loader.py` | YAML → list[dict], `_validate_feed` rejects feeds without URL | `platform/core/feed_loader.py` (multi-vertical: pulls from `verticals/<name>/sources.yaml`) |
| `feed_fetcher.py` | Parallel feedparser pulls, URL canonicalization, per-feed health | `platform/core/feed_fetcher.py` (UA = "Grimoire bot", per-domain rate limit max 1 req/2s) |
| `article_scraper.py` | Full-article scrape (excerpt-only feeds), trafilatura cleaning | `platform/core/article_scraper.py` (adds image/author extraction, language detect, UTC timestamp) |
| `deduplicator.py` | `ShingleIndex` (word-bigram inverted index) + CVE guard | `platform/core/deduplicator.py` (drop CVE guard, swap with vertical-specific guard hooks) |
| `hybrid_classifier.py` | regex first, LLM escalation w/ per-run cap | `platform/core/classifier.py` (reuses pattern; multi-label allowed; budget cap configurable per vertical) |
| `keyword_classifier.py` | Keyword/regex matching with confidence scoring | rolled into `classifier.py` as the regex stage |
| `entities.py` / `ttp_extractor.py` | Cyber-specific entity extraction | `platform/core/entity_extractor.py` (vertical-agnostic; entity types from `verticals/<name>/config.yaml`) |
| `ai_cache.py` | `fcntl`-locked JSON cache keyed by SHA256(content) | replaced by Redis (faster + multi-process safe); same key strategy |
| `llm_client.py` | OpenAI-compatible API, multi-key rotation, circuit breaker | `platform/core/llm_client.py` — port verbatim, parameterise model/base_url |
| `groq_usage.py` | Per-key, per-day, per-caller usage tracking with masked keys | `platform/core/llm_usage.py` (rename for vendor neutrality; same shape) |
| `output_writer.py` | hourly + daily JSON, RSS feed | replaced by `output_renderer.py` (HTML + JSON + RSS + Atom + per-vertical theming) |
| `briefing_generator.py` / `top_stories.py` | tiered AI synthesis | merged into `summarizer.py` (per-article 50-80w, per-cluster 100-150w) + `newsletter_generator.py` |
| `feed_health.py` | per-source success/fail counters, used to render source page | `platform/core/source_health.py` (public `/sources` page on each property) |
| `webhook.py` / `telegram.py` | alert dispatch | replaced by `distribution_engine.py` (newsletter + LinkedIn + Twitter + Reddit queue + HN queue) |
| `safe_http.py` (`install_ssrf_guard`) | DNS rebinding / IMDS protection | port verbatim — install at every process start |
| `cost_tracker.py` | pre-call budget skipping | port; per-vertical budget configurable |

ThreatWatch-specific that Grimoire **does not** copy: `nvd_fetcher`, `epss_enricher`, `kev_enricher`, `attack_tagger`, `actor_profiler`, `victim_tagger`, `darkweb_monitor`, `cve_narrative`, `region_inferrer`, `regions.py`, `ioc_extractor` (all CVE/MITRE-specific). Vested and Modelwatch don't have CVE-equivalents; their entity extraction will use the generic LLM-backed `entity_extractor.py` instead.

---

## 3. Data flow (RSS source → published page)

1. **Feed config** — `verticals/<name>/sources.yaml` (analogue of `config/feeds_*.yaml`). Each entry: `{url, type, region, refresh_interval, priority_weight, category_hints, parser_overrides}`.
2. **Fetch** — feed_fetcher pulls in parallel (default 16 threads), respects per-domain rate limit (max 1 req / 2 s). Tags each entry with feed URL + region. Hashes `title + normalize_url(link)`.
3. **Date filter** — drops entries older than `FEED_CUTOFF_DAYS` (ThreatWatch: 7 days). For news velocity, Grimoire uses 7 days for News, but Reference / Research consume the full corpus.
4. **Dedup** — see §5. Returns `unique_articles` (each with persisted hash) plus `related_articles` lists merged into surviving articles. Persists `seen_hashes.txt` and `seen_titles.txt` in `STATE_DIR`.
5. **Scrape** — for entries whose feed only carried an excerpt, fetch full HTML, clean via trafilatura. SSRF guard rejects internal IPs / .onion / .i2p.
6. **Classify** — hybrid classifier (§6) attaches `category`, `confidence`, multi-label tags from vertical-specific taxonomy.
7. **Cluster** — `story_clusterer` groups articles into stories using dedup similarity + entity overlap + time proximity (Grimoire-specific; ThreatWatch lumps individual articles).
8. **Enrich (LLM tiers)** — out-of-band by default (every 3rd pipeline tick to avoid Groq rate-limit cascades blocking ingestion):
   - Tier 1: per-cluster canonical headline + narrative summary (100-150 words)
   - Tier 2: per-article summary (50-80 words, news-style lede)
   - Tier 3: "why this matters" commentary (1-2 sentences, marked as analysis)
   - Tier 4: daily newsletter digest (top 5 stories)
9. **Persist** — Postgres for the corpus (multi-tenant: every content table has a `vertical_id` column). Redis for LLM cache + queues + rate-limit counters. JSON snapshots in `/srv/grimoire/data/snapshots/<vertical>/{hourly,daily}/` for replication (mirrors ThreatWatch's hourly/daily JSON convention).
10. **Render** — `output_renderer` regenerates HTML on schedule (5-10 min for News, daily for Reference, weekly for Research). Per-vertical theming injected at render time. Outputs: HTML, JSON API, RSS, Atom, sitemap.xml, llms.txt.
11. **Distribute** — `distribution_engine` posts (newsletter via Postmark/Resend, LinkedIn / Twitter / Threads via API, social cards via `social_card_generator`). Reddit and HN are queued for manual operator action — never automated.
12. **Track** — `engagement_tracker` polls each channel daily for likes/shares/click-through, writes to Postgres, surfaces to content prioritisation.

---

## 4. Storage strategy

**ThreatWatch** persists state as flat files (`data/state/seen_hashes.txt`, `seen_titles.txt`, `ai_cache/*.json`, `groq_usage.json`, `scheduler_heartbeat.txt`) and outputs as JSON (`data/output/{hourly,daily}/<timestamp>.json` + `*_latest.json` static aliases) plus RSS. SQLite shows up only on the server container as a read accelerator (`READ_FROM_SQLITE=1`).

**Grimoire** moves the corpus to Postgres for three reasons:
1. Multi-tenant — `vertical_id` partitioning for shared infra without per-vertical container sprawl.
2. Cross-source clustering — story_clusterer needs join-style queries (entity overlap, time proximity) that JSON files don't serve.
3. Engagement tracker — append-only metric ingestion is what relational DBs do well.

State that *doesn't* belong in Postgres stays where ThreatWatch put it:
- LLM response cache → **Redis** (was `fcntl`-locked JSON files; Redis is faster + multi-process safe).
- Per-key rotation index → Redis key `llm:key_index:<provider>`.
- Source health counters → Redis (cheap to read on every fetch).
- Backups → Restic to Cloudflare R2 (`grimoire-backups`, 30-day daily retention then weekly snapshots for 1 year, weekly verify by test restore).

JSON snapshots are still emitted for offsite replication and DR — same hourly/daily cadence ThreatWatch uses.

---

## 5. Word-shingle deduplication (replicate exactly)

This is the algorithm Grimoire copies verbatim from `modules/deduplicator.py`. It's the part of ThreatWatch that's been hardened the longest and the place where wrong dedup creates the most visible bug class (duplicate stories cluttering the front page).

### Normalisation

```python
_PREFIXES = ("breaking:", "update:", "exclusive:", "just in:", "alert:")
_STRIP_TABLE = str.maketrans("", "", string.punctuation)

def normalize_title(title: str) -> str:
    text = title.lower().strip()
    for prefix in _PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    text = text.translate(_STRIP_TABLE)
    return " ".join(text.split())
```

For Grimoire, extend `_PREFIXES` per vertical (Modelwatch picks up "RELEASE:", "PAPER:"; Vested picks up "REPORT:", "FILING:"). Defaults on the platform side.

### Shingles

```python
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "has", "have", "had", "that", "this", "it", "its", "as", "not", "no",
})

def _make_word_shingles(normalized: str) -> frozenset[str]:
    words = [w for w in normalized.split() if w not in _STOP_WORDS]
    if not words:
        return frozenset()
    shingles = set(words)                        # unigrams
    for i in range(len(words) - 1):
        shingles.add(f"{words[i]} {words[i+1]}") # bigrams
    return frozenset(shingles)
```

### Inverted index

`ShingleIndex` keeps three parallel arrays + one dict:
- `_shingle_to_indices: dict[str, list[int]]` — the inverted index.
- `_title_shingles: list[frozenset[str]]` — per-entry shingle set.
- `_normalized_titles: list[str]` — for exact-match short-circuit.
- `_raw_titles: list[str]` — preserved so vertical-specific guards (CVE in TW; in Grimoire: per-vertical entity guards e.g. distinct model names, distinct ticker symbols) can be evaluated.
- `_word_counts: list[int]` — meaningful-word count per entry, used to skip too-short entries.

### Similarity

Overlap ratio (containment):
```python
def _word_overlap_ratio(set_a, set_b) -> float:
    if not set_a or not set_b: return 0.0
    intersection = len(set_a & set_b)
    smaller = min(len(set_a), len(set_b))
    return intersection / smaller if smaller > 0 else 0.0
```

### Lookup logic

```
shingles = _make_word_shingles(incoming)
if word_count(incoming) < _MIN_FUZZY_WORDS (=3):
    return exact_match(incoming, _normalized_titles)

candidates = union of inverted-index hits across all shingles in `shingles`
for idx in candidates:
    if exact match: True
    if word_count(stored[idx]) < 3: skip   # avoid containment false-positives
    if vertical_guard_mismatch(stored[idx], incoming): skip
    if overlap_ratio(shingles, stored[idx]) >= FUZZY_DEDUP_THRESHOLD:
        return True
return False
```

`FUZZY_DEDUP_THRESHOLD` defaults to 0.85 in TW; Grimoire starts at **0.65** for News (per directive — news sources rephrase more aggressively than CVE write-ups), reverts to 0.85 for Reference/Research where wording variation is editorial intent. Configurable per vertical.

### CVE guard → vertical-guard slot

The TW-specific CVE guard (different CVE-IDs ⇒ never duplicate) is generalised in Grimoire. Each vertical can register a `non_dedup_keys: list[regex]` in `verticals/<name>/config.yaml`. When two candidate titles match a guard pattern but yield different captures, they're treated as distinct stories regardless of shingle similarity.

Examples:
- Modelwatch: model identifiers (`(?i)\b(GPT-\d|Claude-\d|Gemini-\d|Llama-\d+)\b`) → distinct model release notes.
- Vested: ticker symbols (`\b[A-Z]{1,5}\b` filtered against an SEC ticker list) and IRS publication numbers (`\bPub(?:lication)?\.?\s*\d+\b`).

### Performance target

`dedup 10K articles in <30s` (per directive). TW hits this comfortably with the inverted-index design — candidate fan-out is limited to titles sharing at least one shingle, and the overlap ratio is O(|A|+|B|).

### Persistence

Per-vertical Redis keys, append + LRU evict:
- `dedup:<vertical>:hashes` (sorted set, score = unix ts; `MAX_SEEN_HASHES = 10_000`)
- `dedup:<vertical>:titles` (sorted set, score = unix ts; `MAX_SEEN_TITLES = 5_000`)

Rolling 7-day window enforced by `ZRANGEBYSCORE … now - 7d` on every load. ThreatWatch uses files; Redis is the multi-vertical-friendly equivalent.

---

## 6. Hybrid classification (regex + LLM escalation)

ThreatWatch's `hybrid_classifier.classify_article()` always runs the keyword classifier first (free), then escalates to the LLM only when:

```python
AI_ESCALATION_CONFIDENCE = 70
AI_ESCALATION_CATEGORIES = {"General Cyber Threat"}  # always-escalate categories
_MAX_ESCALATIONS_PER_RUN = 20  # budget cap, threading.Lock-protected
```

```
escalate iff:
  - LLM provider available, AND
  - escalation_count < cap, AND
  - keyword_result["is_cyber_attack"] == True, AND
  - (category in AI_ESCALATION_CATEGORIES and confidence ≤ 60)
       OR confidence < 70
```

Cache (SHA256("classify:" + title + content[:MAX_CONTENT_CHARS])) before any LLM call. On cache hit, mark `_cached=True` and return. On LLM success, mark `_ai_enhanced=True` and stash original keyword result fields for observability.

**Grimoire generalises:**
- The classifier returns a list of `(label, confidence)` pairs (multi-label) rather than single category.
- Per-vertical taxonomy loaded from `verticals/<name>/config.yaml` — ThreatWatch's hard-coded `is_cyber_attack` boolean becomes `verticals[modelwatch].topics = [model-release, research-paper, ...]` etc.
- Escalation budget cap is per-vertical and per-run; a noisy vertical can't starve a quiet one.
- Multi-LLM provider fallback chain (Groq → Anthropic → cached/keyword-only) is preserved verbatim from TW.

---

## 7. LLM integration patterns (Groq, key rotation, 429/circuit-breaker, caching)

### Key rotation

Multi-key support via env: `LLM_API_KEYS=key1,key2,key3` (comma-separated). Index persisted at `OUTPUT_DIR/.llm_key_index` so round-robin survives container restarts. On 429, advance the key and retry; cap retries at `len(keys)` so one exhausted batch doesn't loop forever.

```python
def _next_api_key():
    if len(LLM_API_KEYS) <= 1: return LLM_API_KEY
    idx = read_int(_key_index_path)
    key = LLM_API_KEYS[idx % len(LLM_API_KEYS)]
    write_int(_key_index_path, (idx + 1) % len(LLM_API_KEYS))
    return key
```

In Grimoire this index lives in Redis (`llm:key_index:<provider>`) so every container sees the same rotation.

### No urllib3 retry layer on LLM HTTP

Critical lesson from TW: when Groq returns 503 with a long Retry-After (load-shedding can be 1-2 hours), urllib3's Retry loop respects it and sleeps the entire duration **per retry**. That single incident stretched ThreatWatch runs to 5+ hours of blocked pipeline time.

```python
def _get_http_session() -> requests.Session:
    return requests.Session()  # no Retry adapter
```

Outer logic rotates keys instead. Grimoire copies this exactly: feed_fetcher uses Retry (transient transport failures fix themselves), llm_client does not.

### Circuit breaker

Process-local; `LLM_CIRCUIT_THRESHOLD=3` consecutive failures trips. Subsequent calls in the same process short-circuit. `reset_circuit()` at the start of each pipeline run keeps the breaker as an in-run blast-radius cap, not a permanent kill switch. Grimoire uses the same threshold.

### Caching

Content-hash keys: `SHA256("<caller_tag>:" + content[:MAX_CONTENT_CHARS])`. ThreatWatch writes `data/state/ai_cache/<hash>.json` with `fcntl.LOCK_EX`. Grimoire moves this to Redis (`llm:cache:<hash>`, TTL 30 days) so it's process-shared and self-evicting.

### Usage tracking

`groq_usage.py` extracts `usage.{prompt_tokens, completion_tokens, total_tokens}` from every response, accumulates per-key + per-caller + per-day, retains 90 days, masks keys to `gsk_xxxx…` so the file is non-reversible if leaked. Grimoire renames to `llm_usage.py` and adds a vertical dimension; otherwise identical.

### Out-of-band enrichment

ThreatWatch runs AI enrichment every 3rd pipeline tick (`AI_ENRICHMENT_EVERY=3`) so a Groq outage doesn't block fetch ingestion. Grimoire keeps this — News fetch every 5-10 min, AI enrichment every ~30 min, Reference / Research generation overnight.

---

## 8. Test approach

ThreatWatch ships ~30 test files in `tests/`, one per module. Conventions:
- `pytest` + `pytest-mock`. No live network in unit tests; HTTP mocked at the `requests` level.
- A `conftest.py` providing fixture data (canned RSS, canned LLM responses).
- Golden-file tests for the classifier (`test_classifier_golden.py`) — title/content pairs with expected labels.
- Coverage tracked via `coverage` (the `.coverage` artifact is committed in TW; Grimoire gitignores it and reports per-CI run).

Grimoire's quality bar is stricter (per directive): ≥ 80% coverage on `platform/core`, mypy clean, ruff clean, every module carries a docstring (purpose / inputs / outputs / dependencies). Same per-module test layout, plus integration tests on a small fixture set (10 sources, 100 articles) replayable end-to-end.

---

## 9. Divergences for news aggregation (Grimoire-specific)

| Capability | ThreatWatch | Grimoire |
|---|---|---|
| Tenancy | Single (cyber) | Multi (modelwatch + vested + N) — every content table carries `vertical_id`; sources, prompts, taxonomy, theming all loaded from `verticals/<name>/`. |
| Cross-source clustering | None — each article stands alone | `story_clusterer` groups by dedup similarity + entity overlap + time proximity. Each story has canonical headline (LLM), source list, primary timestamp, entity list. Importance = cluster_size × source_authority × recency. |
| Entity tracking | CVE / actor / victim modules (cyber-specific) | Generic `entity_extractor` driven by per-vertical entity types (e.g. Modelwatch: `lab, model, person, company, product, paper, tool`). Entity registry persisted; entity-pages auto-generated. |
| Newsletter | None as first-class output (Telegram/webhook are bolt-ons) | `newsletter_generator` is a core module; daily digest weekday 13:00 UTC, top 5 stories, sponsor slot, HTML + plain-text fallback, CAN-SPAM-compliant. Postmark/Resend transport. |
| Content layers | News only | News + Reference + Research + Tools (per-vertical). Each layer has its own generator (`reference_writer`, `research_writer`, `tools_engine`). |
| Distribution | Webhook + Telegram | `distribution_engine` (newsletter, LinkedIn API, Twitter API, Reddit/HN manual queue, Threads/Bluesky optional). Branded social cards via `social_card_generator` (1200×627 LinkedIn, 1200×675 Twitter, 1080×1080 Threads). |
| Engagement signal | None feeds back into prioritisation | `engagement_tracker` polls per-channel metrics daily, surfaces them to story importance. |
| Storage | SQLite read accel + flat JSON | Postgres 16 (corpus, multi-tenant) + Redis 7 (cache/queues/rate-limit) + JSON snapshots (DR + replication only). |
| Output formats | HTML dashboard + RSS | HTML pages + JSON API + RSS + Atom + sitemap + llms.txt + per-tool interactive HTML. |
| Tools layer | None | `tools_engine` renders calculator/comparator/decision-tool YAML to interactive HTML with affiliate hooks. Modelwatch ships ≥5 (LLM cost calculator, token counter, prompt library, model comparison matrix, OSS vs proprietary decision tool). Vested ships ≥5 (RSU+tax, ISO exercise decision, mega-backdoor Roth, comp comparator, FIRE-at-tech-salary, 1099 vs W-2). |

---

## 10. What we're explicitly NOT copying

**Aesthetic.** ThreatWatch's UI is a threat-intelligence dashboard — dense gray, MITRE ATT&CK chrome, region-shaded tables. Grimoire properties are *publications*, not dashboards. UI/UX derivation lives in `design-derivation.md`.

**Cyber-specific enrichers.** NVD / EPSS / KEV / ATT&CK tagger / actor profiler / victim tagger / IOC extractor / darkweb monitor — all stay in ThreatWatch. The cybersecurity vertical (if ever ported into Grimoire) would re-import these as a configuration of `entity_extractor` rather than as standalone modules.

**Single-tenant config files.** ThreatWatch's `config/feeds_*.yaml` live at repo root. Grimoire forbids root-level feed config — every source belongs to a vertical, period.

**Telegram-as-primary-output.** Grimoire's primary owned channel is the newsletter; Telegram (if used at all) is a tertiary social channel.

---

## 11. Module-by-module port plan

Each row is a Phase 2 work item. "Port" = lift from ThreatWatch with minor adaptation. "Build" = new Grimoire module.

| # | Grimoire module | Strategy | Notes |
|---|---|---|---|
| 1 | `feed_loader.py` | Port | Add per-vertical loading; same YAML schema with extra fields (priority_weight, refresh_interval, parser_overrides). |
| 2 | `feed_fetcher.py` | Port | Replace TW UA with Grimoire bot UA (link to `/about`); add per-domain rate limiter (max 1 req/2s) using Redis token bucket. |
| 3 | `article_scraper.py` | Port + extend | Add image extraction, author extraction, language detect, UTC normalisation. |
| 4 | `deduplicator.py` | Port verbatim | Generalise CVE guard to per-vertical regex list; lower default threshold to 0.65 for News. |
| 5 | `classifier.py` | Port + multi-label | Multi-label, per-vertical taxonomy, per-vertical escalation budget. |
| 6 | `entity_extractor.py` | Build | Vertical-typed entities; LLM-backed extraction; persistent per-vertical registry. |
| 7 | `story_clusterer.py` | Build | Dedup similarity + entity overlap + time proximity; canonical headline LLM call. |
| 8 | `llm_client.py` | Port verbatim | Same multi-key rotation, no urllib3 retry, circuit breaker. |
| 9 | `summarizer.py` | Build | Per-article (50-80w) + per-cluster (100-150w) + "why this matters". Strict grounding. |
| 10 | `reference_writer.py` | Build | Glossary / explainer / comparison / beginner-guide. Strict grounding + citations. |
| 11 | `research_writer.py` | Build | Lower volume, longform from accumulated news + reference. |
| 12 | `tools_engine.py` | Build | YAML → interactive HTML calculator/comparator. |
| 13 | `newsletter_generator.py` | Build | Daily digest, sponsor slot, HTML + plain text. |
| 14 | `distribution_engine.py` | Build | Newsletter / LinkedIn / Twitter / Reddit-queue / HN-queue. |
| 15 | `social_card_generator.py` | Build | Templated, no AI imagery. Per-platform aspect ratios. |
| 16 | `engagement_tracker.py` | Build | Daily channel pulls → Postgres → prioritisation signal. |
| 17 | `output_renderer.py` | Build | Per-vertical theming; HTML/JSON/RSS/Atom; SEO-clean URLs. |
| 18 | `monitoring.py` | Port from `feed_health` | Public source health page; story-count metrics; LLM call tracking. |
| — | `safe_http.py` (`install_ssrf_guard`) | Port verbatim | Install at every process start. |
| — | `cost_tracker.py` | Port + extend | Per-vertical budget; pre-call skipping. |
| — | `llm_usage.py` (was `groq_usage`) | Port + extend | Add `vertical` dimension; same masked-key persistence; 90-day retention. |

---

## 12. Open questions logged for later phases

- **Which LLM provider as primary for Grimoire?** ThreatWatch uses Groq for the cheap-fast tier. Directive says "Groq client (free tier, primary)". Decision: same. Anthropic remains as fallback for complex reference/research synthesis where Groq small models drift on grounding. Cost-routing decision lives in Phase 2 `llm_client.py`.
- **Postgres schema.** Phase 2 work; multi-tenant table layouts, FK strategy, partial indexes per vertical — all decided when the modules are built.
- **Snapshot retention.** ThreatWatch keeps 7 days of hourly + 30 days of daily on disk. Grimoire keeps 1 day hourly + 14 days daily on disk; longer-term retention lives in R2 via Restic.
- **Source authority weights.** ThreatWatch uses categorical priority. Grimoire uses numeric weights (per directive: 0.6–1.0 with category bands). Specific numbers for Modelwatch live in `verticals/modelwatch/sources.yaml`.

---

*End of derivation. Phase 0b (`design-derivation.md`) covers UI/UX and visual identity — explicitly anti-ThreatWatch in aesthetic, even though the engine underneath is its descendant.*
