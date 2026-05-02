# Security Posture — Grimoire

**Captured:** 2026-05-02
**Audience:** anyone touching the grimoire platform (operators, future agents).
**Principle:** security must not break the product. Every control here exists
to protect users and revenue while keeping build/ship/serve fast. If a
control adds friction without removing real risk, it's wrong and gets
reverted. (Same operating philosophy as atelier's `SECURITY.md`.)

---

## 1. Threat model

| Threat | Likelihood | Impact | Defence |
|---|---|---|---|
| Origin VPS compromise | Low | High (corpus + sponsorship inquiries + subscriber records) | UFW default-deny, fail2ban on sshd, no Tier-A creds on box, R2 backup off-box, key-only root login |
| Cloudflare account takeover (when DNS lands) | Very low | Catastrophic (DNS + R2) | 2FA on CF account; CF Global Key never on the exposed server; rotation on suspected leak |
| Container escape | Low | High (host) | No privileged containers; mem/cpu limits; postgres + redis bound to 127.0.0.1 only |
| Site defacement | Low | Medium | All HTML regenerated from Postgres on every cron tick; nightly backup; restore in <10 min |
| DDoS | Medium (post-launch) | Low (CF will absorb when wired) | Caddy timeouts (read_header 10s, max_header_size 16KB); per-domain rate limit at fetch layer; static origin doesn't compute per-request |
| Credential leak via git/logs | Medium | Variable by tier | Tiered cred policy; .gitignore; .env mode 600; pre-commit scan |
| Supply-chain (PyPI/Docker poisoning) | Low | Medium | Pinned majors in `requirements.txt`; Docker images pinned by tag |
| SSRF via feed URL | Low | High (cloud IMDS access) | `engine/core/safe_http.py` — process-wide urllib3 monkeypatch rejects RFC1918/loopback at connect time, closing the DNS-rebinding TOCTOU |
| Hostile feed XML | Low | Low | feedparser parses defensively; no XML eval; SSRF guard catches redirects to internal IPs |

Out of scope:
- Nation-state targeting (impractical for this scale).
- Physical access to the VPS (provider's responsibility).
- Insider threats from the operator account.

---

## 2. Trust zones

```
COMMAND CENTER  —  deploy@sqx-automation
  - Only place that holds Tier-A creds (Cloudflare, R2 keys, registrar)
  - Drives R2 backups, deploys, ops
  - Never exposed to public internet
        |
        | ssh (key-only, port 2222)
        v
GRIMOIRE PROD VPS (178.104.214.16)
  - Runs all verticals + shared infra (postgres, redis, caddy)
  - Holds Tier-B (.env mode 600, gitignored) and Tier-C (own SSH host key)
  - UFW default-deny except 2222/80/443; fail2ban on sshd
        |
        | Caddy + docker bridge (grimoire_internal)
        v
Containers
  - All on private bridge; bound to 127.0.0.1:5432 / 6379
  - Postgres + Redis: never reach the public internet
  - mem_limit + cpus on every service
```

The command center is the only privileged actor. Grimoire is treated as
if it could be compromised tomorrow.

---

## 3. Credential tier model

| Tier | Definition | Where it lives | Examples |
|---|---|---|---|
| **A** | Cross-resource, blast radius beyond the box | Command center only (`~/Documents/server_credentials.txt`, mode 660) | Cloudflare Global API Key, R2 access keys, registrar API tokens, Stripe live secret, Postmark/Resend tokens |
| **B** | Runtime-scoped, blast radius bounded by the box | mode-600 `.env` on the server, gitignored | DB password (DB only on internal bridge), session secrets, magic-link signing key, LLM API keys (per-vertical budgets cap blast radius) |
| **C** | The box's own identity | The box itself | SSH host keys, Caddy auto-TLS account key (when DNS lands) |

**Memory enforced:** `feedback_credentials_tier_a_command_center_only.md`
in the project memory.

---

## 4. Network architecture

- **UFW** default-deny incoming. Allows `2222/tcp` (sshd), `80/tcp`, `443/tcp` only. No `tcp/22`. No outbound restrictions (engine fetches public feeds).
- **sshd** listens on port 2222 only. `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PermitRootLogin prohibit-password`. ssh.socket disabled (Ubuntu 24.04 socket-activation footgun documented in `feedback_ssh_port_change_avoid_socket_override.md`).
- **fail2ban** with sshd jail, 5 retries / 10 min / 1h ban.
- **Caddy** terminates HTTP for every public hostname; security headers globally (HSTS, X-Content-Type-Options, X-Frame-Options DENY, Referrer-Policy, Permissions-Policy). Slow-loris guarded via timeouts.
- **Docker** `grimoire_internal` private bridge. Postgres + Redis bound to `127.0.0.1` only — unreachable from the public internet.
- **SSRF guard** installed at every process start (`safe_http.install_ssrf_guard()`).

---

## 5. Application-layer controls (Phase 7 audit)

| Control | State | Evidence |
|---|---|---|
| All secrets in `.env`; never in code or git history | ✅ | `.gitignore` excludes `.env`, `*.env`, `.r2-*.env`. Pre-commit scan documented in `BUILD-DIRECTIVE.md`. |
| Postgres on internal-only bridge | ✅ | `docker-compose.yml` binds `127.0.0.1:5432`. |
| No exposed admin paths on public hostnames | ✅ | `/api/admin` and `/sponsorship/admin` `Disallow:` in robots.txt; FastAPI handler (Phase 4 next batch) will enforce auth. |
| Magic-link tokens single-use, 15-minute expiry | 🟡 | Schema in `pro_users`; handler arrives with FastAPI app. |
| CSRF protection on all forms | 🟡 | Same — FastAPI handler will use `starlette-csrf` or itsdangerous-signed tokens. |
| Rate limiting on all public endpoints | 🟡 | Per-domain rate limiter exists at fetch layer; public-API rate limit lands with FastAPI app. |
| Parameterized queries only | ✅ | SQLAlchemy 2.0 ORM + `select()` constructs throughout `engine/core/*`; no raw SQL. |
| All user input escaped in templates | ✅ | Jinja2 `select_autoescape(["html", "xml"])` (`output_renderer._env`). |
| Stripe webhook signature verification | 🟡 | Handler arrives with FastAPI; `STRIPE_WEBHOOK_SECRET` placeholder in `.env.example`. |
| Newsletter unsubscribe tokens unguessable | ✅ | `subscribers.unsubscribe_token` is unique String(64); the FastAPI signup handler will populate it via `secrets.token_urlsafe(48)`. |
| Audit log for admin actions | 🟡 | Phase 4 work; `pro_users.updated_at` and `sponsor_inquiries.responded_at` give first-pass observability. |
| No PII in logs (sanitize emails) | 🟡 | Pipeline / harness logs do not log emails. FastAPI handler will mask emails on logging. |
| OWASP Top 10 documented | ✅ | This document (§§1–7). |

Legend: ✅ in place, 🟡 scaffolded — full enforcement arrives with FastAPI handler in the next batch.

---

## 6. Data privacy + retention

Mirrors `/privacy` (the public statement) so technical reality matches the
declared posture (per BUILD-DIRECTIVE termination criterion #8).

| Data | Storage | Retention |
|---|---|---|
| Server access logs | `/var/log/caddy/*.log`, `/var/log/grimoire/*.log` | 30 days, then deleted (logrotate, Phase 8 setup) |
| Self-hosted analytics aggregates | TBD self-hosted Plausible/Umami container | 12 months, then archived |
| Newsletter subscribers | Postgres `subscribers` table — `email_hash` (SHA256 hex) for lookup, `email_encrypted` Fernet blob for delivery | until unsubscribe; +30 days then deleted |
| Pro-tier customers | Postgres `pro_users` table | until account closure; +7 years for tax-receipt records |
| Sponsorship inquiries | Postgres `sponsor_inquiries` table | until responded + 18 months |
| LLM call cache | Redis `llm:cache:*` keys | TTL 30 days, self-evicting |
| Dedup state | Redis `dedup:<vertical>:hashes` / `:titles` | rolling 7-day window, LRU-evicted at MAX_SEEN limits |

---

## 7. Backup posture

- Local leg: nightly `pg_dumpall` to `/srv/grimoire/backups/postgres/` at 03:30 UTC; 14-day retention.
- Off-box leg: restic to Cloudflare R2 `grimoire-backups` bucket — **pending operator R2 setup** (see `ops/runbooks/backup.md`).
- Backup encrypted at rest by `RESTIC_PASSWORD`; R2 token bucket-scoped + IP-allowlisted.
- Weekly verification by test-restore of one snapshot to a throwaway scratch DB.

---

## 8. Pre-launch security checklist

- [ ] `.env` mode 600, owner deploy, no `.env` in git.
- [ ] No exposed admin endpoints reachable on the public hostnames.
- [ ] Stripe live key in `.env` not in code or commit history; webhook signature secret set.
- [ ] Magic-link signing key rotated to a fresh 32-byte secret on first use.
- [ ] R2 backup leg active; weekly restore drill scheduled.
- [ ] Status push monitor in Uptime Kuma (status.auvalabs.com); alert channel configured.
- [ ] CSP per-vertical reviewed (currently inline-style allowed; tighten to nonce-based once FastAPI app lands).
- [ ] No PII visible in `/var/log/caddy/*.log` after a one-week tail.

---

## 9. Incident response

| Scenario | Action |
|---|---|
| Suspected SSH compromise | Rotate root password (kept in `~/Documents/server_credentials.txt`); regenerate operator SSH key; review fail2ban + auth.log; restore from R2 if integrity in doubt. |
| Cloudflare account leak | Out-of-band password change + 2FA reset; rotate every Tier-A cred; audit recent zone changes. |
| Stripe webhook secret leak | Rotate webhook signing key in Stripe dashboard; update `.env`; invalidate any in-flight signed payloads. |
| LLM key leak | Per-key revocation (Groq/Anthropic dashboards); pipeline rotates to remaining keys via `llm_client._next_api_key`; new keys to `.env`. |
| Postgres dump corruption | Restore from latest local dump (`/srv/grimoire/backups/postgres/dumpall-*.sql.gz`); if local also bad, restore from R2 via the command-center driver. |

---

## 10. Open items

- **Phase 4 wiring:** FastAPI app for `/api/subscribe`, `/api/sponsor`, `/auth/magic-link`, `/api/tools/*/calculate`. Brings 🟡 controls in §5 to ✅.
- **Synthesize API key drop:** unlocks the LLM-graded dimensions of the Phase 6 harness (content quality, source attribution, editorial integrity).
- **R2 bucket + token:** activates the off-box backup leg.
- **CSP tightening:** move from `style-src 'unsafe-inline'` to a nonce-based policy once the FastAPI app is the canonical request entry.
- **Domain commit + auto-TLS:** swap `<vertical>.local` placeholders for the real domains and let Caddy auto-issue Let's Encrypt certs via Cloudflare DNS-01.
