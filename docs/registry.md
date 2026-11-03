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
| `/api/v1/coa-summary` | COA catalogue and project-coverage summary |
| `/api/v1/coa-reports` | Indexed official COA report records |
| `/api/v1/procurement-summary` | Procurement evidence and coverage summary |
| `/api/v1/procurement-records` | Exact official procurement evidence records |
| `/api/v1/contract-outcomes` | Deterministic procurement-to-delivery cross-checks |

## Published dataset contract

The current production snapshot contains 68,608 positive GAA records, 56,887
DPWH delivery records, 385 explicitly unreviewed candidate links, five reviewed
dossiers and one quarantined example. Exact artifact hashes and monetary totals
are verified by the live contract in `cloudflare/busisi/scripts/verify-live.mjs`.
The COA pilot separately indexes four official report records and records a
completed coverage review for all six dossiers. No project-level COA observation
match is currently claimed, and no COA source copy is marked archived.
The contract outcome layer currently compares the three dossiers with exact
procurement evidence against their DPWH delivery records. It also retains three
exact rows extracted from BetterGov's version-pinned PhilGEPS mirror, including
the source revision and a canonical SHA-256 for each extracted row. Those rows
support secondary awardee-name and amount comparisons only. The complete
Parquet file and original PhilGEPS award pages are not archived, so a delivery
contractor is not presented as an officially verified awardee. Missing
inspection and payment evidence remains unavailable.

The canonical ingestion database remains local and is never reachable through
the Worker. D1 contains only publication records derived from reconciled source
artifacts.

Last updated: 2026-11-03.
