# Grimoire Build Directive — v2 (LOCKED)

**Server:** grimoire-auvalabs-01 (Hetzner Cloud CPX 32, Falkenstein, fresh Ubuntu 24.04 LTS)
**Reference architecture:** https://github.com/AuvaLabs/threatwatch (study patterns, do NOT copy UI/UX)
**Mission:** Build a multi-vertical knowledge platform that ships **Modelwatch** (AI/ML) first and **Vested** (personal finance for tech workers) within 60 days. Platform must support N additional verticals via configuration.
**Operating mode:** Fully autonomous. Pre-authorized decision-making within this directive's scope. Do not pause for routine confirmations.
**Termination:** Both Modelwatch and Vested are live, scoring above quality threshold, monetization paths active, with the platform ready for additional verticals.

---

## Strategic context (read once, internalize)

This is the news/knowledge content arm of a diversified portfolio targeting $20K MRR for operator's resignation. Combined portfolio at 12 months realistically produces $20-40K MRR; Grimoire properties are projected to contribute $10-25K of that.

**Verticals are configuration, not rebuilds.** The platform is multi-tenant from day one. Adding a third or fourth vertical is a config job.

**Operator constraint:** vibe coding after work, 15-25 hours/week. AI handles 99% of content production; human supervises quality and monetization.

**Brand architecture (Auva Labs invisible):**
- Each property is a fully independent brand to consumers
- Auva Labs FZE appears only in Terms of Service and Privacy Policy as the operating legal entity (regulatory minimum)
- No umbrella branding, no "Auva Labs network" footers, no cross-promotion structure
- No parent-brand social presence
- Properties may occasionally reference each other when genuinely editorial, but not systematically

**Geographic targeting:** US-first, with UK/Canada/Australia as secondary. Tier 1 CPM markets are the audience target.

**Content rules (locked):**
- Text + image only (NO video)
- Images optional per story
- AI photorealism banned
- Allowed: source-attributed images (with permission), curated stock photography, AI-generated diagrams/charts/abstract illustrations (clearly editorial), data visualizations
- Auto-generated templated social cards for every post

**Distribution channels (locked):**
- Newsletter (owned channel, primary)
- LinkedIn (primary for finance/career/B2B verticals)
- Twitter/X (primary for AI/cyber/tech verticals)
- Reddit (community-specific, manual posting queue, NO automation)
- Hacker News (manual submission only)
- Threads, Bluesky, Mastodon (secondary)

**4-layer content architecture per vertical (locked):**
1. **News** — real-time aggregation, drives daily-return traffic
2. **Reference** — evergreen explainers, glossary, beginner guides; durable SEO asset
3. **Research** — original analysis, longform, state-of-X reports; credibility layer
4. **Tools** — calculators, comparators, decision aids; highest commercial intent

---

## Phase 0 — Foundation reading

### Phase 0a — Architecture reference

Clone or web_fetch https://github.com/AuvaLabs/threatwatch. Document in `/srv/grimoire/docs/architecture-derivation.md`:
- Module structure (feed_loader, feed_fetcher, deduplicator, classifier, etc.)
- Data flow (RSS source → indexed entry → output)
- Storage strategy
- Word-shingle deduplication algorithm (replicate exactly)
- Hybrid classification logic (regex + LLM escalation)
- LLM integration patterns (Groq, key rotation, 429 failover, caching)
- Test approach

Document divergences for news aggregation:
- Multi-tenant (multiple verticals on one platform)
- More aggressive cross-source clustering
- Entity tracking over time
- Newsletter generation as first-class output
- 4-layer content (not just news)

### Phase 0b — UI/UX reference study

Modelwatch and Vested are publications, not dashboards. Visual identity must NOT match ThreatWatch's threat-intelligence dashboard aesthetic.

Use web_fetch to study and document patterns to borrow vs reject:

**Primary structural reference:**
- https://www.techmeme.com — story prioritization, source clustering, indented related coverage, type-driven hierarchy

**Editorial polish reference:**
- https://stratechery.com — typography, restrained color, sense of editorial seriousness

**Information density:**
- https://news.ycombinator.com — type-driven hierarchy without chrome

**Story format reference:**
- https://www.axios.com — "Smart Brevity" pattern (headline → why it matters → bullets → sources)

**Aesthetic spirit:**
- https://www.are.na — restrained editorial design, generous whitespace
- https://search.marginalia.nu — slow-web library aesthetic

**Curation voice:**
- https://thebrowser.com — source attribution treatment

**Anti-references (do NOT design like):**
- TechCrunch, The Verge (ad-stuffed tech press)
- Generic AI startup landing pages
- Substack default theme
- News sites with paywall popups, autoplay video, cookie consent walls
- Threat intelligence dashboards (including ThreatWatch's aesthetic)
- AI-generated hero illustrations

Write 800-1200 word design rationale at `/srv/grimoire/docs/design-derivation.md`:
- Exact typography choices
- Exact color palette (hex values, both themes)
- Per-property accent colors
- Grid/layout approach
- Key UI patterns being borrowed

**Per-property accent color recommendations (commit to one each):**
- Modelwatch: warm muted amber (#B8743A or similar) — fits Grimoire codename, differentiates from "every AI uses purple"
- Vested: deep teal (#2D5F5D or similar) — finance-appropriate, distinct from Modelwatch
- Future verticals: pick distinct color per property

---

## Phase 1 — Server foundation

Provision grimoire-auvalabs-01 from fresh Ubuntu 24.04 LTS. Idempotent.

### System hardening
- UFW firewall: 22 (or moved port), 80, 443; deny all else
- Fail2ban for SSH brute force
- Automatic security updates
- Non-root operator user with sudo, SSH key only auth, password auth disabled
- SSH on non-default port (e.g., 2222)
- 4GB swap, swappiness=10
- tmpfs for /tmp

### Set hostname
```bash
sudo hostnamectl set-hostname grimoire-auvalabs-01
```

### Docker + Compose
- Latest stable Docker Engine + Compose plugin
- Operator user in docker group
- Daemon log rotation (max 10MB, 3 files per container)
- Custom networks per stack

### Caddy reverse proxy
- Caddy 2 with automatic HTTPS via Let's Encrypt
- Cloudflare API integration for DNS-01 challenge (multi-domain)
- Per-domain config in `/srv/grimoire/caddy/sites/`
- Security headers globally: HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy
- Strict CSP per-site
- Access logs to `/var/log/caddy/` with rotation
- Hardened against slow-loris

### Postgres 16
- Containerized via Docker Compose
- Volume at `/srv/grimoire/data/postgres`
- Strong password from environment
- Internal Docker network only
- Nightly backup to `/srv/grimoire/backups/postgres/`
- Schema multi-tenant (vertical_id column on all content tables)

### Redis 7
- LLM response caching, queue management, rate limiting
- Containerized
- AOF persistence every second
- 512MB limit, allkeys-lru eviction

### Backup infrastructure
- Restic for encrypted backups
- Daily backup to Cloudflare R2 (bucket: grimoire-backups)
- Weekly verification by test restore
- 30-day daily retention, then weekly snapshots for 1 year

### Observability
- Push monitoring to status.auvalabs.com (existing Uptime Kuma)
- Per-container health checks
- Structured JSON logging to `/var/log/grimoire/`

### Per-container resource limits
- mem_limit and cpus on every service
- Total committed memory <80% of available RAM

### Directory layout

```
/srv/grimoire/
├── docs/
│   ├── architecture-derivation.md
│   ├── design-derivation.md
│   ├── runbook.md
│   ├── monetization-strategy.md
│   ├── editorial-policy.md
│   ├── security-posture.md
│   └── BUILD-DIRECTIVE.md (this file)
├── platform/                      # Vertical-agnostic shared code
│   ├── core/
│   ├── shared/
│   └── tests/
├── verticals/
│   ├── modelwatch/
│   ├── vested/
│   └── _template/
├── ops/
│   ├── harness/
│   ├── deploy.sh
│   ├── backup.sh
│   └── runbooks/
├── caddy/
│   ├── Caddyfile
│   └── sites/
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

### Domain configuration

Operator handles outside this directive:
- DNS: modelwatch.com (or .ai if .com unavailable) → grimoire-auvalabs-01 IP
- DNS: vested.financial (priority 1), getvested.com (priority 2), vested.money (priority 3) → grimoire-auvalabs-01 IP
- Cloudflare HTML caching enabled on all zones

### Phase 1 deliverable
- Server hardened
- Docker + Compose ready
- Caddy serving HTTPS placeholder pages on all domains
- Postgres + Redis ready
- Directory layout populated with stubs
- Sentinel `index.html` showing "Property launching soon"

Commit. Tag: `phase-1-foundation`.

---

## Phase 2 — Core platform engine

Build multi-tenant news aggregation engine. All modules in `platform/core/` are vertical-agnostic.

### Modules

**1. feed_loader.py** — loads sources from `verticals/<name>/sources.yaml`. Source types: RSS, Atom, JSON Feed, Twitter/X (via API or RSS bridges), HuggingFace blog, GitHub releases, ArXiv categories, custom scrapers. Each source: URL, type, refresh interval, priority weight, category hints, parser overrides.

**2. feed_fetcher.py** — parallel fetching (8-thread default), per-domain rate limiting (max 1 req/2sec), conditional GET (ETag, Last-Modified), timeout handling, exponential backoff, source health tracking. UA identifies as Grimoire bot with about page link.

**3. article_scraper.py** — fetch full article when feed only provides excerpt. HTML cleaning via trafilatura. Image extraction. Author extraction. Publish timestamp normalization (UTC). Language detection.

**4. deduplicator.py** — word-shingle inverted index (replicate ThreatWatch implementation). Configurable similarity threshold (start 0.65 for news). Rolling 7-day window. Returns story clusters. Performance target: dedup 10K articles in <30 seconds.

**5. classifier.py** — hybrid: regex-first (cheap), LLM escalation (ambiguous). Topic taxonomy from `verticals/<name>/config.yaml`. Confidence scoring. Multi-label allowed.

**6. entity_extractor.py** — extract named entities. Per-vertical entity registry. Cross-link articles to entities for entity-page generation.

**7. story_clusterer.py** — groups articles into stories using dedup similarity + entity overlap + time proximity. Each story: canonical headline (LLM-generated), source list, primary timestamp, entity list. Importance = cluster size × source authority × recency.

**8. llm_client.py** — Groq client (free tier, primary). Smart key rotation. 429 failover with exponential backoff. Request caching by content hash (Redis). Prompts loaded from `verticals/<name>/prompts/`. Structured output (JSON) where possible. Cost tracking.

**9. summarizer.py** — per-article summaries (50-80 words, news-style lede). Per-story narratives (cluster-level, 100-150 words). "Why this matters" commentary (1-2 sentences, optional, marked as analysis). **Strict grounding: summary must derive from source text. No facts beyond source.** Source citation maintained.

**10. reference_writer.py** — generates evergreen reference articles. Glossary entries, explainer articles, comparison articles, beginner guides. **Strict grounding: must cite verifiable sources.** Outputs reviewed by quality harness before publishing.

**11. research_writer.py** — generates longform research from accumulated news + reference data. State-of-X reports, retrospectives, original analysis. Lower volume, higher effort.

**12. tools_engine.py** — calculator/comparator/decision-tool definitions per vertical. Each tool defined in YAML with inputs, formula, references. Renders interactive HTML. Affiliate placement hooks per tool.

**13. newsletter_generator.py** — daily digest. Top 5 stories. Sponsor placement slot. HTML email + plain text fallback. CAN-SPAM compliant unsubscribe.

**14. distribution_engine.py** — multi-channel:
- Newsletter: render and send via Postmark/Resend
- LinkedIn: post via API (300-500 word format with hook, value, CTA, AI-generated from canonical content)
- Twitter/X: post threads (5-10 tweets, AI-generated from canonical content) via API
- Reddit: queue for MANUAL posting (do NOT automate; surface in operator dashboard with suggested subreddit and post text)
- Hacker News: queue for manual submission
- Threads, Bluesky: optional, similar to Twitter

**15. social_card_generator.py** — auto-generates branded social cards per platform aspect ratio (1200×627 LinkedIn, 1200×675 Twitter, 1080×1080 Threads). Templated, no AI imagery. Property branding + headline + property logo.

**16. engagement_tracker.py** — pulls metrics from each channel daily (likes, shares, comments, click-through, newsletter opens). Stores in Postgres. Surfaces signal to content prioritization.

**17. output_renderer.py** — server-side renders all pages. No SPA. Static HTML regenerated on schedule (every 5-10 min for news, daily for reference, weekly for research). Multiple output formats: HTML, JSON API, RSS, Atom. Per-vertical theming injected at render. SEO-friendly clean URLs.

**18. monitoring.py** — source health endpoint, story count metrics, LLM call tracking, error logging with context, public status subset.

### Quality bar
- Test coverage ≥ 80% on platform/core
- Type hints throughout (mypy clean)
- Linting clean (ruff)
- Each module: docstring (purpose, inputs, outputs, dependencies)
- Integration tests on small fixture set

Commit, tag `phase-2-core-engine`.

---

## Phase 3 — Modelwatch vertical (first to ship)

### Domain
- modelwatch.com if available, else modelwatch.ai

### Sources (verticals/modelwatch/sources.yaml)

Build 60-80 sources across categories. Validate every URL. Document signal-to-noise expectations.

**AI labs (priority 1.0):** OpenAI blog, Anthropic news, Google DeepMind, Meta AI, Mistral, Cohere, AI21, Stability AI, Inflection, xAI, NVIDIA AI, Microsoft Research AI, Apple ML Research, Amazon Science, IBM Research AI, Hugging Face blog

**Research aggregators (0.9):** ArXiv cs.CL, cs.LG, cs.AI, cs.CV, cs.NE, stat.ML; Papers with Code; Connected Papers feeds

**Tech press AI (0.8):** TechCrunch AI, The Verge AI, Ars Technica AI/ML, IEEE Spectrum AI, Wired AI, VentureBeat AI

**AI newsletters/blogs (0.85):** Import AI, The Batch, Last Week in AI, Ben's Bites, TLDR AI, Lenny's (AI), One Useful Thing, Interconnects, AI Snake Oil

**Independent voices (0.7):** Simon Willison's blog, Latent Space Pod RSS, individual researcher posts

**Community signals (0.6):** r/MachineLearning hot (top 10/day), r/LocalLLaMA hot, HuggingFace trending models, HuggingFace daily papers, GitHub trending in AI repos, HN AI/ML posts (score >100)

**Regulatory and policy (0.85):** Brookings, AEI, CSET AI policy, EU AI Act updates, US Executive Orders on AI, UK AISI publications

### Modelwatch taxonomy

Topics: model-release, research-paper, funding, product-launch, regulation, controversy, safety-research, benchmark, hiring, infrastructure, application, tool-release, commentary

Entity types: lab, model, person, company, product, paper, tool

### Modelwatch reference layer (REQUIRED for launch)

**AI/ML glossary (50+ entries):**
What is RAG, What is fine-tuning, What is RLHF, What is a transformer, What is MoE, What is LoRA, What is quantization, What is inference, What is a token, What is context window, What is alignment, What is interpretability, What is an embedding, What is a vector database, What is a vision transformer, What is multimodal, What is a foundation model, What is supervised fine-tuning, What is reinforcement learning, What is in-context learning, etc.

Each entry: 200-400 word definition, "why it matters", related terms (cross-linked), references, last-verified date.

**Beginner's guides (5-10):**
- Beginner's guide to large language models
- How AI agents actually work
- How to evaluate AI models
- Understanding the AI lab landscape
- AI training vs inference: why both matter

**Comparison pages (3-5):**
- GPT-4 vs Claude vs Gemini: capability comparison
- Open-source vs proprietary AI models: trade-offs
- Cloud AI APIs: pricing and capabilities compared

### Modelwatch tools layer (5+ at launch)
- LLM cost calculator
- Token counter (multi-tokenizer)
- Prompt library (curated, by use case)
- Model comparison matrix (live data)
- Open-source vs proprietary decision tool

### Modelwatch research layer (1+ at launch, then quarterly)
- "State of AI Q1 2026" — synthesized from accumulated news + reference data, with charts and analysis

### Modelwatch LLM prompts (verticals/modelwatch/prompts/)

Required: summarize_article, cluster_canonical_headline, cluster_narrative, extract_entities, classify_topic, why_this_matters, daily_digest, glossary_entry, explainer_article, comparison_article, beginners_guide_section, research_synthesis, social_card_text, linkedin_post, twitter_thread

All prompts: deterministic (low temperature), structured JSON output, grounding instructions, citation requirements.

### Modelwatch design

Apply design rationale from Phase 0b:
- Typography: Newsreader (Google Fonts) for body serif, National Park or GT America for sans (test, pick one)
- Accent: warm muted amber (#B8743A)
- Light theme: warm off-white #FBFAF7, near-black #1A1A1A
- Dark theme: warm dark #1A1817, warm off-white #EEEAE3
- Iconography: Phosphor Icons
- No AI photorealism
- Dense, editorial, scannable; closer to Techmeme than TechCrunch

### Modelwatch pages required

- `/` — front page (Techmeme-style story prioritization)
- `/today` — chronological today's stories
- `/story/<slug>` — story page (cluster of sources)
- `/topic/<slug>` — topic-filtered view
- `/entity/<type>/<slug>` — entity timeline
- `/glossary/` — glossary index
- `/glossary/<term>` — individual entry
- `/learn/` — beginner's guides hub
- `/learn/<guide>` — individual guide
- `/compare/` — comparison hub
- `/tools/` — tools hub
- `/tools/<tool>` — individual tool
- `/research/` — research index
- `/research/<piece>` — research articles
- `/about` — what Modelwatch is, mission
- `/methodology` — sourcing, AI usage transparency, editorial policy
- `/sources` — full transparent source list
- `/privacy` — data practices (identifies Auva Labs FZE — minimum legal disclosure)
- `/terms` — terms of service (identifies Auva Labs FZE)
- `/sponsorship` — sponsorship pitch
- `/newsletter` — signup
- `/api` — API documentation
- `/feed.rss`, `/feed.json`, `/sitemap.xml`, `/robots.txt`, `/llms.txt`

Commit, tag `phase-3-modelwatch-launched`.

---

## Phase 4 — Monetization layer (Modelwatch)

### Newsletter (free tier)
- Daily digest, weekday at 13:00 UTC
- One sponsor slot per issue (clearly labeled "Sponsored")
- Email capture every page
- Postgres `subscribers` table (pseudonymized)
- One-click unsubscribe (CAN-SPAM)
- Send via Postmark or Resend

### Pro tier (paid)

Pricing:
- Free: daily digest, dashboard, RSS
- Pro $19/mo or $190/yr: early access (digest 6h earlier), no sponsor sections, advanced filters, weekly deep-dive, API access (low rate limit), priority support
- Team $79/mo for up to 10 seats
- Enterprise (custom)

Stripe integration: Checkout for self-serve, Customer Portal for management, webhooks update Postgres.

Auth: magic-link email (no passwords). Token single-use, 15-minute expiry.

### Sponsorship infrastructure
- Daily digest sponsor slot
- Dashboard front-page sponsor slot
- Sponsorship inquiry form → operator email
- Pricing at /sponsorship: single-issue $750, weekly $3000, monthly $10000 (launch pricing)
- Sponsorship admin behind auth
- Audience profile, example placements, contact

### Affiliate placements
- AI tool recommendations on relevant stories (only tools you'd use, disclosed)
- Course/book recommendations on glossary/learn (Coursera, O'Reilly, MIT Press) — disclosed
- Footer + per-page disclosure

### Analytics
- Self-hosted Plausible or Umami (containerized on grimoire server)
- Page views, referrers, search terms, conversion to newsletter signup, conversion to Pro
- No third-party trackers

Commit, tag `phase-4-modelwatch-monetized`.

---

## Phase 5 — Vested vertical (60 days after Modelwatch)

### Domain
- vested.financial (priority 1)
- getvested.com (priority 2)
- vested.money (priority 3)
- If unavailable, document and pick best alternative

### Vested positioning
- Audience: Software engineers, data scientists, AI researchers, technical founders earning $100K-$500K
- Voice: technical-minded, data-driven, honest about tradeoffs, no fluff, no get-rich-quick
- Differentiation: every other PF site treats tech workers as one audience among many. Vested makes them the ONLY audience.
- Coverage: equity compensation (RSUs, ISOs, NSOs, ESPP), tax planning (AMT, QSBS, mega backdoor Roth), tech-industry-specific risks (layoffs, vesting, golden handcuffs), brokerage decisions, FIRE math at tech salaries

### Sources for Vested

**Direct sources (1.0):**
- IRS publications
- SEC filings (when relevant)
- FRB economic data
- Treasury (yields, T-bills)
- Major brokerage announcements (Fidelity, Schwab, Vanguard, Robinhood, Public, Wealthfront)
- Tax software releases (TurboTax, FreeTaxUSA changes)

**Tech compensation data (0.9):**
- Levels.fyi blog
- Pay-related Reddit posts in r/cscareerquestions (signal-filtered)
- Major company comp announcements (when public)

**PF press (0.8):**
- WSJ Personal Finance
- NYT money/finance
- Bloomberg personal finance

**PF creators/blogs (0.7):**
- Mr. Money Mustache
- ChooseFI blog
- Physician on FIRE
- The White Coat Investor (parallel high-income professional audience)
- Reddit r/financialindependence top posts

**Tech-specific finance (0.85):**
- Holistic Wealth (finance for engineers)
- Engineer's Codex (finance-relevant)
- High-income tech worker subreddit signals

### Vested taxonomy

Topics: equity-compensation, taxes, retirement-planning, brokerage-investing, real-estate, debt-management, salary-negotiation, layoff-strategy, financial-independence, side-income, banking, credit, insurance-life-stage, charitable-giving, estate-planning

Entity types: brokerage, bank, credit-card, tax-software, insurance-provider, employer (compensation refs)

### Vested reference layer (REQUIRED for launch)

**PF-for-tech-workers glossary (50+ entries):**
What is RSU, What is ISO, What is NSO, What is ESPP, What is QSBS, What is 83(b) election, What is AMT, What is mega backdoor Roth, What is deferred compensation, What is Section 174, What is 1031 exchange, What is wash sale, What is tax-loss harvesting, What is HSA, What is FSA, What is 401(k), What is Roth IRA, What is Traditional IRA, What is Solo 401(k), What is QBI deduction, What is Schedule C, What is Schedule K-1, etc.

**Beginner's guides (5-10):**
- Understanding RSU vesting and taxation
- ISO vs NSO: which equity grant is better
- Mega backdoor Roth: a complete guide for tech workers
- Layoff financial preparation playbook
- FIRE math for tech salaries

**Comparison pages:**
- Best brokerages for tech workers (Fidelity vs Schwab vs Vanguard)
- Premium credit cards: Amex Platinum vs Chase Sapphire Reserve for tech professionals
- Tax software: TurboTax Premier vs FreeTaxUSA for stock-comp returns

### Vested tools layer (5+ at launch)

- RSU vesting + tax calculator (federal + state, AMT-aware)
- ISO exercise decision tool (cash needed, AMT impact, holding period)
- Mega backdoor Roth contribution calculator
- Tech compensation comparator (TC, base, bonus, equity at FAIR market values)
- FIRE-at-tech-salary calculator
- 1099 vs W-2 take-home comparator (for engineer freelancers)

### Vested affiliate stack (apply during Phase 5)

- Brokerages: Fidelity, Schwab, Robinhood, Public, Wealthfront, M1 Finance
- Premium credit cards: Amex (referral), Chase (referral), Capital One (referral)
- Tax software: TurboTax (Intuit affiliate), H&R Block, FreeTaxUSA
- Banking: SoFi, Wealthfront Cash, Marcus, Mercury (engineer-founder banking)
- Insurance: Policygenius, Lemonade
- Real estate: Roofstock, Fundrise, Arrived
- RSU/equity tools: Equitybee, Carta (employees), Secfi

### Vested design

Apply design rationale; Vested-specific:
- Typography: same family as Modelwatch (consistency at platform level even though brands appear independent)
- Accent: deep teal (#2D5F5D) — finance-appropriate, distinct from Modelwatch
- Tone: more conservative than Modelwatch (financial content has higher trust bar)

### Vested pages required

Same structure as Modelwatch (front page, story pages, glossary, learn, compare, tools, research, about, methodology, etc.)

Plus Vested-specific:
- `/equity/` — comprehensive equity compensation hub
- `/tax/` — tax planning hub
- `/calculators/` — alias for /tools/ (finance audiences search "calculator")

### Vested LLM prompts

Same structure as Modelwatch but Vested-specific. Critical addition: every prompt for tax/legal content must include "this is general information not professional advice" framing in the output.

Commit, tag `phase-5-vested-launched`.

---

## Phase 6 — Quality harness and continuous audit

`/srv/grimoire/ops/harness/` — same patterns as atelier harness.

### Quality dimensions (100 points per page)

| Dimension | Weight | Measures |
|---|---|---|
| HTML & meta integrity | 12 | Valid HTML5, complete meta, OG, Twitter cards, canonical |
| SEO signals | 12 | hreflang where applicable, JSON-LD schema, sitemap, internal linking |
| AEO signals | 10 | llms.txt accurate, FAQPage where applicable, machine-readable structure |
| Content quality | 15 | Summaries grounded in sources, no hallucinations, attribution complete |
| Source attribution | 10 | Every fact linked, source authority indicated |
| Editorial integrity | 10 | No clickbait, analysis disclosed, paid content marked |
| Performance | 10 | Page weight <250KB, FCP <1.5s, no render-blocking |
| Accessibility | 10 | WCAG 2.1 AA: contrast 4.5:1, alt text, focus states, touch targets, keyboard nav |
| Privacy posture | 5 | Privacy claims match technical reality |
| Monetization tasteful | 6 | Ads/sponsors visible but not invasive, disclosure clear |

Quality threshold: 87/100 per page. Below = work item.

### Fact-grounding correctness

For news: every claim in generated summary must be traceable to source text. Sample 50 summaries weekly, verify. Pass criterion: 100% claims grounded.

For Vested specifically (YMYL content):
- Tax law claims verified against IRS publications
- Brokerage feature claims verified against current documentation
- Dollar figures fresh (auto-update or last-verified-date)
- Editorial review (human spot-check) on calculator outputs weekly

### Source health monitoring
- Each source SLO: successful fetch within 24 hours
- Sources with consecutive failures > 5 auto-disabled
- Public source health visible at /sources page

### The loop

```
Loop forever:
  Run full harness audit
  Generate report at ops/harness/reports/<timestamp>.md
  Identify highest-priority work item
  Execute: build, fix, optimize
  Re-audit affected pages
  Commit
  If portfolio score > 87 and no critical issues: continue to next vertical/feature
  Else: continue loop
```

Commit, tag `phase-6-harness-active`.

---

## Phase 7 — Security hardening

- All secrets in `.env`, never in code, never in git history
- Postgres only on Docker internal network
- No exposed admin paths on public domains
- Magic-link auth tokens single-use, 15-minute expiry
- CSRF protection on all forms
- Rate limiting on all public endpoints
- Parameterized queries only
- All user input escaped in templates
- Stripe webhook signature verification
- Newsletter unsubscribe tokens unguessable
- Audit log for admin actions
- No PII in logs (sanitize emails)
- OWASP top 10 documented and addressed

### llms.txt and robots.txt — honest declaration

Each property's llms.txt declares:
- What the property is
- How content is sourced (aggregation + AI summarization with grounding)
- What's tracked (analytics, opt-out path)
- What's monetized (sponsorship, premium tier, affiliates with disclosure)
- Editorial methodology link
- Operating entity (Auva Labs FZE — minimum legal disclosure)

Commit, tag `phase-7-security-hardening`.

---

## Phase 8 — Launch readiness

### Pre-launch checklist (per property)

- [ ] Domain DNS resolves
- [ ] HTTPS valid
- [ ] Cloudflare configured
- [ ] Postgres backed up nightly to R2
- [ ] Restic backups verified by test restore
- [ ] Status page push monitoring active
- [ ] Rate limiting tested
- [ ] All sources fetching successfully
- [ ] Dedup ratio sensible on real data
- [ ] LLM summaries spot-checked: 20 random verified for grounding
- [ ] Reference layer: 50+ glossary entries, 5+ guides, 3+ comparisons live
- [ ] Tools layer: 5+ tools live and tested
- [ ] Research layer: 1+ piece live (state-of-X)
- [ ] Newsletter signup → confirmation → first daily digest works end-to-end
- [ ] Pro tier signup → Stripe checkout → access granted works end-to-end
- [ ] Sponsor inquiry form delivers
- [ ] Mobile responsive
- [ ] Lighthouse: Performance > 90, Accessibility > 95, Best Practices > 95, SEO > 95
- [ ] Cross-browser verified
- [ ] Submitted to Google Search Console, Bing Webmaster Tools
- [ ] Sitemap submitted
- [ ] All harness checks passing portfolio score > 87
- [ ] llms.txt comprehensive
- [ ] Privacy policy reflects technical reality, identifies Auva Labs FZE
- [ ] Terms of service drafted, identifies Auva Labs FZE
- [ ] About page describes property mission (does NOT mention Auva Labs in marketing context)
- [ ] Methodology page transparent about AI usage and source policy
- [ ] Newsletter unsubscribe works
- [ ] No PII in logs
- [ ] No exposed admin endpoints
- [ ] No leaked secrets in committed files
- [ ] Distribution module tested: posts test article to LinkedIn, Twitter test accounts; queues Reddit/HN for manual

### Launch announcement preparation

Drafts at `/srv/grimoire/docs/launch/<property>/`:
- Hacker News "Show HN" submission with link, brief description, what's interesting
- Subreddit-specific posts: r/MachineLearning for Modelwatch (if rules allow), r/cscareerquestions or r/personalfinance for Vested
- LinkedIn announcement (operator's personal account, NOT Auva Labs)
- Twitter/X announcement thread

Commit, tag `phase-8-launch-ready`.

---

## Termination conditions

You stop when ALL of:

1. Modelwatch Phase 8 launch-ready checklist 100% complete
2. Vested Phase 8 launch-ready checklist 100% complete
3. Portfolio harness score > 87 averaged across all pages on both properties
4. Modelwatch ingesting 60+ sources successfully
5. Vested ingesting 30+ sources successfully
6. Both properties' newsletter signup-to-delivery works with real email
7. Both properties' Stripe Pro tier signup-to-access works with real payment
8. Both properties' sponsor inquiry forms deliver
9. Backups verified by test restore
10. Status monitoring active
11. Documentation complete: architecture-derivation, design-derivation, runbook, monetization-strategy, editorial-policy, security-posture
12. Vertical template tested: walk through "add cybersecurity-extended vertical" mentally — steps clear and bounded

You do NOT stop because:
- Session getting long (checkpoint, summarize, continue)
- "It seems good enough" (only the harness decides)
- "Maybe the user wanted X different" (this directive is the directive)
- External service slow (work around or document dependency)

---

## Decisions you make autonomously

Make the call, document why, continue:

- Specific font choices within editorial direction
- Specific accent color hex within recommended ranges
- Specific source priority weightings within ranges
- Specific LLM prompt wording (within constraints: grounded, structured, news-style)
- Specific page layout details within editorial direction
- Specific Pro tier feature subset for v1
- Specific newsletter sending time within sensible range
- Specific sponsorship pricing for launch
- Database schema details
- Caching strategy details
- Test framework details (pytest, ruff, mypy as defaults)
- Logging format details
- Specific tools to build per vertical (within minimum count requirements)
- Specific glossary entries (within minimum count requirements)
- Domain selection from priority list

---

## Decisions you escalate

Stop and ask only for:

- A factual claim that requires verification beyond your capability
- A legal posture decision (e.g., a Terms clause with real legal weight)
- A monetization decision affecting brand identity
- A breaking-change to atelier or another existing Auva Labs property
- A security finding suggesting compromise
- A decision to spend money beyond clear authorization (servers, domains, transactional email tiers, Stripe fees pre-authorized; anything beyond requires confirmation)
- A decision to change this directive

---

## What "good" looks like at completion

The operator can:
- Visit modelwatch.com and find a polished, real-time AI/ML knowledge platform with news + reference + research + tools
- Visit vested.financial (or chosen domain) and find a polished personal-finance-for-tech-workers knowledge platform with same 4-layer architecture
- Sign up for either newsletter, receive a real digest the next weekday at 13:00 UTC
- Sign up for either Pro tier, immediately receive Pro features
- Submit a sponsorship inquiry, have it land in operator email
- Read methodology pages and understand exactly how the system works
- Read llms.txt and find honest declarations
- See harness reports demonstrating quality is being measured
- Run `./ops/deploy.sh <vertical>` and have any code change deploy with audit harness pre-deploy
- Read documentation and understand how to add a third vertical themselves
- Trust that the platform is production-grade

The operator should look at this and say "this is genuinely two real products on a real platform, not demos."

---

## Operating ethics (non-negotiable)

- Never invent facts. If a summary cites a number not in source, summary is wrong. Fix prompt, regenerate.
- Never hide AI usage. Methodology page transparent. llms.txt honest.
- Never display ads or sponsors deceptively. Always labeled, distinguishable from editorial.
- Never copy without attribution. Every story links back to original sources prominently.
- Never collect more data than needed.
- Never break privacy posture you declare.
- Never compromise security for velocity.
- Never recommend a product you wouldn't use.
- Never cross-promote between Auva Labs properties as if they're independent. Editorial mentions allowed; systematic cross-promotion forbidden.

---

## Final operating note

You have everything you need. Reference architecture at the GitHub URL. Strategic context locked. Quality bar documented. Termination defined. Decisions pre-authorized within scope.

Begin Phase 0a.
Then Phase 0b.
Then sequential phases through Phase 8.

When termination conditions met, write `/srv/grimoire/docs/build-complete.md` summarizing: what was built, what's live, what's measurably good, recommended operator first-review priorities, recommended next-30-days operations cadence.

Build with care. Quality compounds. Sloppy execution defeats the entire thesis.

Begin.
