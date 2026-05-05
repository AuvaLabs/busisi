# Launch readiness checklist

**Captured:** 2026-05-02
**Scope:** Modelwatch + Vested. Each property has its own section below;
shared infrastructure items appear once at the top.

A property may launch when every box in its section is ticked. Items
gated on the operator (DNS, billing accounts, API keys) are flagged
**[OP]**; items the engine handles or has handled are flagged **[ENG]**.

---

## Shared infrastructure (one-time, blocks both launches)

- [x] **[ENG]** Hardened Ubuntu 24.04 VPS (`grimoire-auvalabs-01`) — UFW default-deny, SSH on 2222, key-only, fail2ban, unattended-upgrades, 4G swap.
- [x] **[ENG]** Docker + Postgres 16 + Redis 7 healthy.
- [x] **[ENG]** Caddy serving placeholder hostnames (`modelwatch.local`, `vested.local`) over HTTP. Security headers global.
- [x] **[ENG]** Local nightly Postgres dump (03:30 UTC, 14-day retention).
- [x] **[ENG]** Cloudflare R2 bucket `grimoire-backups` provisioned (account `22fe4279...`, S3-compatible). `ops/backup.sh` pushes via aws CLI when `AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY` are present.
- [ ] **[OP]** R2 API token (bucket-scoped) added to `/srv/grimoire/.env`; install `awscli` on VPS. Verify with one-shot `sudo /srv/grimoire/ops/backup.sh`.
- [ ] **[OP]** Status push monitor in `status.auvalabs.com` Uptime Kuma; populate `UPTIME_PUSH_URL` in `/srv/grimoire/.env`; alert channel (Discord/Telegram) wired.
- [ ] **[OP]** Synthesize / Groq API key(s) → `LLM_API_KEYS=` in `.env`. Unlocks LLM-driven Phase 2 modules + Phase 6 LLM-graded harness dimensions.
- [ ] **[OP]** Postmark or Resend API token → `POSTMARK_API_TOKEN=` in `.env`. Newsletter delivery.
- [x] **[ENG]** FastAPI handler app shipped (Phase 9): `/api/subscribe`, `/api/sponsor`, `/api/tools/<slug>/calculate`, `/api/v1/{health,articles,entities}`, `/r/<partner>/<slug>` (affiliate redirect).
- [x] **[ENG]** Caddy reverse-proxies `/api/*`, `/r/*`, `/confirm`, `/unsubscribe` → `127.0.0.1:8001` per vertical site block (was a pre-existing bug — fixed this session).
- [ ] **[OP]** Domain commit. Update Caddyfile + `output_renderer._canonical_url` from `.local` to the real domains. Cloudflare DNS A-record to `178.104.214.16`. CF cache-HTML rule.

## Monetization + AI-citation surface (this session)

- [x] **[ENG]** robots.txt allow-list for AI crawlers (PerplexityBot, GPTBot, ClaudeBot, Google-Extended, etc.) under explicit licensing terms.
- [x] **[ENG]** `/llms.txt` + `/llms-full.txt` content index for AI ingestion.
- [x] **[ENG]** `/feed.json` (JSON Feed v1.1) peer to RSS.
- [x] **[ENG]** Organization JSON-LD with `sameAs` (LinkedIn, GitHub) on every page.
- [x] **[ENG]** BreadcrumbList + NewsArticle (`author: Organization`) JSON-LD.
- [x] **[ENG]** FAQPage JSON-LD on `/methodology` (5 Q&A pairs for AEO).
- [x] **[ENG]** `/.well-known/rsl.json` — Really Simple Licensing manifest.
- [x] **[ENG]** `/.well-known/security.txt` — RFC 9116 (1-year Expires auto-rolled).
- [x] **[ENG]** `/licensing` — plain-English peer to rsl.json.
- [x] **[ENG]** `/advertise` — sponsorship + ads + affiliate rate card (no premium, per pivot).
- [x] **[ENG]** Affiliate macro `_affiliate.html` + `/r/<partner>/<slug>` redirect with UTM + click logging (`affiliate_clicks` table).
- [x] **[ENG]** Per-vertical `partners.yaml` registry (placeholder ref codes).
- [x] **[ENG]** Bot UA logging — Caddy log → `bot_hits` table via `engine.core.bot_log_parser`, wired into cron.
- [ ] **[OP]** Replace `?ref=auvalabs` placeholders in `verticals/{modelwatch,vested}/partners.yaml` with real affiliate codes before commercial use.
- [ ] **[OP]** Verify LinkedIn slug `https://www.linkedin.com/company/auvalabs/` in `base.html` Organization JSON-LD; correct if different.
- [ ] **[OP]** Apply to Perplexity Publisher Program (needs ≥30 days indexed clean).
- [ ] **[OP]** Apply to TollBit + Cloudflare Pay-Per-Crawl after ≥30 days of bot_hits telemetry.
- [ ] **[OP]** Carbon Ads / EthicalAds applications when traffic crosses thresholds.

---

## Modelwatch

- [x] **[ENG]** All 9 page paths return 200 via Host header (`/`, `/about`, `/methodology`, `/privacy`, `/terms`, `/sources`, `/tools/`, `/llms.txt`, `/robots.txt`, `/sitemap.xml`).
- [x] **[ENG]** Cron pipeline ingesting + persisting + rendering every 10 min.
- [x] **[ENG]** 44 active sources (4 disabled pending URL audit).
- [x] **[ENG]** Postgres `articles` accumulating real OpenAI / Google / etc. articles.
- [x] **[ENG]** Quality harness ≥ 87 (currently 95.7%).
- [x] **[ENG]** llms.txt declares sourcing + AI usage + monetisation + opt-out.
- [x] **[ENG]** Privacy policy reflects technical reality, identifies Auva Labs FZE.
- [x] **[ENG]** Terms of service drafted, identifies Auva Labs FZE. **DRAFT — operator legal review pending.**
- [x] **[ENG]** Methodology page transparent about AI usage + source policy.
- [x] **[ENG]** Tools layer: 1 of 5 minimum live (LLM cost calculator). **4 more to ship before launch:** token counter, prompt library, model comparison matrix, OSS vs proprietary decision tool.
- [ ] **[ENG]** Reference layer: 50+ glossary entries, 5+ guides, 3+ comparisons. **Gated on Synthesize API** (LLM-drafted, editorially reviewed).
- [ ] **[ENG]** Research layer: 1+ piece live ("State of AI Q1 2026"). **Gated on Synthesize API.**
- [ ] **[ENG]** LLM summaries spot-checked: 20 random verified for grounding. Gated on Synthesize API.
- [ ] **[ENG]** Newsletter signup → confirmation → first daily digest works end-to-end. Gated on FastAPI app + Postmark.
- [ ] **[ENG]** Pro tier signup → Stripe checkout → access granted works end-to-end. Gated on FastAPI app + Stripe.
- [ ] **[ENG]** Sponsor inquiry form delivers. Gated on FastAPI app + email transport.
- [ ] **[ENG]** Distribution module tested: posts test article to LinkedIn, Twitter test accounts; queues Reddit/HN for manual.
- [ ] Cross-browser verified (Chrome, Safari, Firefox, mobile).
- [ ] Lighthouse: Performance > 90, Accessibility > 95, Best Practices > 95, SEO > 95.
- [ ] **[OP]** Submitted to Google Search Console + Bing Webmaster Tools. Sitemap submitted.
- [ ] **[OP]** No leaked secrets in committed files (manual review of `git log -p` against `cfat_`, `cfk_`, `AKIA`, `GOCSPX`, etc.).

---

## Vested

- [x] **[ENG]** All 9 page paths return 200 via Host header.
- [x] **[ENG]** Cron pipeline running for vested alongside modelwatch (multi-tenant promise verified — same engine, two tenants).
- [x] **[ENG]** 27 active sources (8 disabled pending URL audit).
- [x] **[ENG]** Vertical row seeded in Postgres (id=2).
- [x] **[ENG]** Quality harness ≥ 87 (currently 95.7%).
- [x] **[ENG]** Teal accent (`#2D5F5D` / `#5A8E8C`) renders correctly.
- [x] **[ENG]** llms.txt + robots.txt + sitemap.xml live.
- [x] **[ENG]** Privacy + terms identify Auva Labs FZE. **DRAFT — operator legal review pending.**
- [ ] **[ENG]** Tools layer: 0 of 5 live. **Need 5 before launch:** RSU+tax calc, ISO exercise decision, mega-backdoor Roth, comp comparator, FIRE-at-tech-salary, 1099 vs W-2 take-home.
- [ ] **[ENG]** Reference layer (50+ glossary, 5+ guides, 3+ comparisons). Gated on Synthesize API.
- [ ] **[ENG]** Research layer (1+). Gated on Synthesize API.
- [ ] **[ENG]** YMYL editorial-review checkpoint added to harness for tax/retirement/estate topics. Gated on Synthesize API.
- [ ] **[ENG]** Newsletter / Pro tier / sponsor flows end-to-end. Gated on FastAPI + Postmark + Stripe.
- [ ] **[ENG]** Distribution module test posts.
- [ ] Cross-browser + Lighthouse pass.
- [ ] **[OP]** Search Console + Bing Webmaster + sitemap submission.

---

## Launch sequence (when all checklist items above pass)

1. **Pre-launch.** Snapshot Postgres + Redis. Run harness one final time; archive the report tag-stamped with the launch git tag.
2. **DNS.** Point real domain A-record to `178.104.214.16` at Cloudflare. Grey-cloud first, verify HTTP works, switch to orange-cloud (Full Strict SSL).
3. **Caddy.** Update `caddy/Caddyfile` site blocks with the real hostnames + `tls { dns cloudflare {env.CF_API_TOKEN} }`. `systemctl reload caddy`. First request triggers Let's Encrypt issuance via DNS-01.
4. **Smoke.** `curl https://<domain>/` returns 200; `cf-ray` header present; `Server` header stripped.
5. **Indexing.** Submit sitemap to Google Search Console + Bing Webmaster Tools. Trigger IndexNow ping.
6. **Announcement (sequenced 24h apart).** See `docs/launch-announcements.md`. HN Show first; LinkedIn next; Twitter thread; Reddit (r/MachineLearning for Modelwatch, r/personalfinance for Vested) third day. Threads/Bluesky/Mastodon as a single batch on day four.
7. **Watch.** First-72-hours observation window. Source health, harness score, sponsor-inquiry inbox, Pro-tier signups, error logs.
8. **Tag.** `git tag launch-modelwatch-<date>` / `launch-vested-<date>`.
