# Busisi service registry

## Production

| Component | Value |
|---|---|
| Public domain | `busisi.org` |
| Worker | `busisi-publication` |
| Publication database | D1 `busisi-publication` |
| Static assets | Workers Assets bound to the publication Worker |
| Rate limit | 120 requests per 60 seconds |
| Monitor | `.github/workflows/busisi-production-monitor.yml`, every six hours |

The Worker has no model, KV or R2 binding. The monitor is read-only and holds
no deployment credentials.

## Public API

| Endpoint | Purpose |
|---|---|
| `/healthz` | Read-only service health |
| `/api/v1/stats` | Source counts and artifact identity |
| `/api/v1/budgets` | GAA source-record search |
| `/api/v1/delivery` | DPWH delivery-record search |
| `/api/v1/candidates` | Explicitly unreviewed candidate search |
| `/api/v1/projects` | Reviewed and quarantined dossier register |
| `/api/v1/projects/<slug>` | Evidence dossier lookup |
| `/api/v1/projects.csv` | Filtered reviewed-register export |

## Published dataset contract

The current production snapshot contains 68,608 positive GAA records, 56,887
DPWH delivery records, 385 explicitly unreviewed candidate links, five reviewed
dossiers and one quarantined example. Exact artifact hashes and monetary totals
are verified by the live contract in `cloudflare/busisi/scripts/verify-live.mjs`.

The canonical ingestion database remains local and is never reachable through
the Worker. D1 contains only publication records derived from reconciled source
artifacts.

Last updated: 2026-11-03.
