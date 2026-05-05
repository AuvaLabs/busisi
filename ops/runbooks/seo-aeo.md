# SEO + AEO + GEO runbook

Operational how-to for the search/discovery layer: IndexNow (Bing,
Yandex), Google Search Console + Bing Webmaster (domain-property
verification via CF DNS), Cloudflare Web Analytics, and AI-bot
monitoring. Read alongside `docs/strategy.md` (Phase 6) and the launch
checklist.

## Tier-0 once-per-domain setup

For each new domain (V3+):

```
# 1. CF API token (Tier-A, one-time, ~/kb_center/server_credentials.md)
#    Scopes: Zone:DNS:Edit, Account:Web Analytics:Edit
export CF_API_TOKEN=...
export CF_ACCOUNT_ID=22fe4279ad540a78456e6e4c82e62a1f

# 2. Register zone with CF Web Analytics (auto-injects beacon)
ops/cf_web_analytics.sh <zone_id> <host>

# 3. Verify GSC domain property
#    a) GSC > Add Property > Domain > paste apex (e.g. embedding.report)
#    b) GSC shows: "google-site-verification=AbCdEf..."
#    c) Add it via CF API:
ops/cf_dns_txt.sh <zone_id> <host> 'google-site-verification=AbCdEf...'
#    d) Click Verify in GSC

# 4. Verify Bing Webmaster Tools domain
#    Same flow: BWT > Add Site > paste apex; BWT shows TXT value.
ops/cf_dns_txt.sh <zone_id> <host> 'verify.bing.com=...'

# 5. Submit sitemap (after a successful render)
#    GSC: Sitemaps > add /sitemap.xml
#    BWT: Sitemaps > add https://<host>/sitemap.xml
```

## IndexNow (Bing + Yandex push-mode indexing)

IndexNow is a free, key-based protocol that lets you push new URLs to
Bing/Yandex within minutes instead of waiting for crawl-mode discovery
(hours to days). We run it automatically every pipeline tick.

### How it's wired

- `engine/core/indexnow.py` — module
- `engine/core/output_renderer.py:render_meta_files()` — emits
  `<KEY>.txt` to `data/output/<vertical>/<KEY>.txt` so IndexNow's
  verifier can fetch it from `https://<host>/<KEY>.txt`
- `ops/run_pipeline.sh` — runs `python -m engine.core.indexnow <V>` after
  `bot_log_parser`, which pings IndexNow with the day's new URLs
  (default: last 24h, max 50 URLs, skip-tier excluded, front-page
  always included)

### Per-vertical key

Auto-generated on first run at `verticals/<name>/.indexnow_key` (mode
600, gitignored). To rotate:

```
ssh grimoire 'rm /srv/grimoire/verticals/<name>/.indexnow_key'
# next pipeline tick generates a new key + re-emits the verifier file
```

### Manual pings

```
ssh grimoire 'cd /srv/grimoire && PYTHONPATH=. .venv/bin/python -m \
  engine.core.indexnow embedding --dry-run'
# or for real
ssh grimoire 'cd /srv/grimoire && PYTHONPATH=. .venv/bin/python -m \
  engine.core.indexnow embedding'
```

Exit code 0 on success (HTTP 200/202); 2 on hard error. Pipeline
treats indexnow as fail-open (`|| echo ...`) — Bing's API hiccupping
must not block the rest of the pipeline.

### Verifying IndexNow accepts the key

```
curl -fsSI https://<host>/<KEY>.txt
# 200 with text/plain body == verifier file is reachable
```

If 404, the renderer hasn't run yet, or the file got pruned. Run
`ops/run_pipeline.sh <vertical>` once.

## Cloudflare Web Analytics

Free, privacy-first (no cookies, no fingerprinting, no consent banner
required under GDPR/CCPA). Auto-installed on proxied zones — no
template edit, no JS to maintain.

### Enable

```
CF_API_TOKEN=... CF_ACCOUNT_ID=... \
  ops/cf_web_analytics.sh <zone_id> <host>
```

### Inspect

CF Dashboard > Analytics & Logs > Web Analytics > select host. Pageviews,
visits, top paths, top referrers, country breakdown. Refreshed ~5min
lag.

### Disable

CF Dashboard > Web Analytics > Site > Settings > Disable. (No CLI
shipped — disabling is rare.)

## AI-bot monitoring

We log every Caddy-proxied request whose User-Agent matches an AI
crawler (GPTBot, ClaudeBot, PerplexityBot, etc.) into the `bot_hits`
table via `engine/core/bot_log_parser.py`, which `run_pipeline.sh` runs
each tick.

```
ssh grimoire 'sudo -u postgres psql grimoire -c \
  "SELECT user_agent, COUNT(*) FROM bot_hits \
   WHERE seen_at > NOW() - INTERVAL '\''7 days'\'' \
   GROUP BY 1 ORDER BY 2 DESC LIMIT 20"'
```

After ~30 days of data:

- Apply to Perplexity Publisher Program (rev-share for citations)
- Apply to TollBit / Cloudflare Pay-Per-Crawl (per-fetch licensing)

## SEO/AEO/GEO surfaces (already live)

| Surface | Path | Purpose |
|---|---|---|
| Sitemap | `/sitemap.xml` | crawler discovery |
| Robots | `/robots.txt` | allow AI crawlers + RSL pointer |
| RSS | `/feed.rss` | classic feed readers |
| JSON Feed | `/feed.json` | modern feed readers + AI ingest |
| LLM index | `/llms.txt` | top-level URL list for AI |
| LLM full | `/llms-full.txt` | full-text bundle for AI |
| RSL | `/.well-known/rsl.json` | machine-readable licensing |
| Security | `/.well-known/security.txt` | RFC 9116 contact |
| API | `/api/v1/articles` | structured read-only access |

## Health checks

```
# 1. IndexNow verifier reachable
curl -fsSI https://embedding.report/$(cat /srv/grimoire/verticals/embedding/.indexnow_key).txt

# 2. Sitemap reachable
curl -fsSI https://embedding.report/sitemap.xml

# 3. CF Web Analytics beacon present (proxied zones only)
curl -fsS https://embedding.report/ | grep -o 'static.cloudflareinsights.com'

# 4. JSON-LD valid (paste a /story/<slug>/ page into:)
#    https://search.google.com/test/rich-results
```

## Failure modes seen

- **CF DNS TXT propagation lag.** GSC verification can fail if you click
  Verify before CF edges sync; wait 60s and retry.
- **IndexNow returns 422 "Invalid key location".** Means the
  `<KEY>.txt` verifier file isn't reachable at the expected URL —
  check the renderer ran and the key on disk matches the file name.
- **CF Web Analytics auto_install requires proxied=true.** If a record
  is set to "DNS only" (gray cloud), the beacon isn't injected.
  `dig +short A <host> @1.1.1.1` should return CF anycast IPs (104.x or
  172.x), not the origin VPS IP.
