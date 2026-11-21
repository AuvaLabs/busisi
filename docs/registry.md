# Busisi service registry

## Production

| Component | Value |
|---|---|
| Public domain | `busisi.org` |
| Worker | `busisi-publication` |
| Publication database | D1 `busisi-publication` |
| Static assets | Workers Assets bound to the publication Worker |
| Project evidence media | Private R2 `busisi-project-evidence` |
| Rate limit | 120 requests per 60 seconds |
| Monitor | `.github/workflows/busisi-production-monitor.yml`, every six hours |

The Worker has no model or KV binding. Its R2 binding is read-only application
access to archived project-image objects. D1 publication state gates each media
response, so quarantined objects cannot be served by a guessed object key. The
monitor is read-only and holds no deployment credentials.

## Public API

| Endpoint | Purpose |
|---|---|
| `/healthz` | Read-only service health |
| `/api/v1/stats` | Source counts and artifact identity |
| `/api/v1/questions` | Evidence question catalogue with answerability, scope, current counts, and limitations |
| `/api/v1/public-services-summary` | Reconciled title-classification controls for school and health-facility records |
| `/api/v1/facility-registry-status` | Latest DepEd source check and measured facility-link release gate |
| `/api/v1/public-services` | Filtered budget-stage rows and delivery contracts with facility, work-type, and evidence-flag classifications |
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
| `/api/v1/contract-evidence` | Contract lifecycle document-acquisition status |
| `/api/v1/acquisition-coverage` | Reconciled full-contract-universe acquisition controls |
| `/api/v1/coverage-status` | Latest gated project-image coverage release |
| `/api/v1/source-monitor-status` | Latest deterministic source-revision monitor result |
| `/api/v1/senate-committee` | FY2027 Senate committee watch or fully checked project changes |
| `/api/v1/community-needs-summary` | PSA 2024 population coverage and published source limits |
| `/api/v1/community-needs` | Searchable PSA population and household counts by official place code |

## Senate committee-stage contract

The committee endpoint currently publishes a watch state for Committee Report
No. 131 and HB 10858. It publishes no project count or peso amount until the
official report and complete schedules are saved, hashed, checked by page, and
reconciled to every published project row. Missing values remain `null`, never
zero. Uncertain project links stay outside the public change table.

## Community needs context

The first community needs release contains 43,768 official PSA place rows from
the 2024 Census of Population. This includes 18 regions and 42,011 barangay
rows. The national table reports 112,729,484 people. The 18 regional tables add
to 112,727,776 people, which is 1,708 fewer. Household population and household
counts match the national controls exactly. Busisi preserves the difference and
does not assign it to a region.

The PSA CAR response also contains 1,148 appended Region II rows. They are
excluded because their geographic codes fall outside CAR. All published place
codes remain unique, every included lower-level row is attached to a matching
parent code, and each published parent-child total matches. These source limits
are returned by the summary endpoint.

This layer is context for budget questions. It is not part of the integrity
signal calculation and does not label a project, contractor, agency or public
official as suspicious. No individual CBMS response is collected or published.

## Published dataset contract

The current production snapshot contains 68,608 positive GAA records, 56,887
DPWH delivery records, 385 explicitly unreviewed candidate links, five reviewed
dossiers and one quarantined example. Exact artifact hashes and monetary totals
are verified by the live contract in `cloudflare/busisi/scripts/verify-live.mjs`.
The COA pilot separately indexes five official report records and records a
completed coverage review for all six dossiers. All five official PDFs are
saved with verified hashes and page counts. No project-level COA observation
match is currently claimed.
The contract outcome layer currently compares the three dossiers with exact
procurement evidence against their DPWH delivery records. It also retains three
exact rows extracted from BetterGov's version-pinned PhilGEPS mirror, including
the source revision and a canonical SHA-256 for each extracted row. Those rows
support secondary awardee-name and amount comparisons only. The complete
Parquet snapshot is now archived, but original PhilGEPS award pages are not, so
a delivery contractor is not presented as an officially verified awardee. Missing
inspection and payment evidence remains unavailable.
The contract evidence ledger adds 27 explicit lifecycle checks across the three
contracts. Its current status distribution is one verified and archived
official artifact, three blocked official-source acquisitions queued for
retry, three version-pinned secondary mirror rows and 20 target documents not
located. A PMR-reported signed-contract or Notice-to-Proceed date is retained as
a reported event only and is not counted as acquisition of that document.

The full acquisition universe scans all 56,887 current DPWH delivery contracts.
It classifies 38,110 as structured exact matches, 6,884 as exact IDs found in
titles, 2,077 as multiple exact rows, 161 as conflicting identifiers, and 9,655
as having no exact mirror row. All 511,983 lifecycle tasks are held in a local
SQLite queue. D1 receives only reconciled aggregate controls and provenance.

The canonical ingestion database remains local and is never reachable through
the Worker. D1 contains only publication records derived from reconciled source
artifacts.

The public question catalogue derives its counts and dates from those same D1
release controls. It separates answerable questions, incomplete coverage, and
unsupported claims. Reader actions lead to explanatory evidence desks, while
the JSON endpoint exposes the catalogue as a machine-readable evidence contract.

The public-services inventory currently classifies 6,050 records: 937 FY2027
budget-stage rows and 5,113 FY2024 to FY2026 delivery contracts. The controls
reconcile to 4,722 school-related records, 671 hospital records and 657
health-center records. These are source rows, not unique physical facilities.
The classification version and full counting boundary are returned with the
summary endpoint and verified by the production contract.

Project-image coverage begins with the reviewed dossier baseline and expands
through a resumable evidence queue. Each contract is checked against the
project-detail and image-list endpoints, with original source responses and
JPEGs archived before publication. Exact count matches may be published,
conflicts remain quarantined, and explicit zero-image responses stay visible as
coverage results. Images are served from private R2 by immutable internal URLs.
The live coverage page is the current source for release counts.

Last updated: 2026-11-16.
