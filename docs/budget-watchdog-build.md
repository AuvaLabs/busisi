# Philippine budget watchdog build contract

## Objective

Build an evidence-first public system that traces Philippine appropriations
through procurement and project implementation. The system highlights records
that deserve review without presenting a risk signal as proof of wrongdoing.

## Data lineage

The canonical lineage is:

1. Previous-year General Appropriations Act
2. Current National Expenditure Program
3. House General Appropriations Bill
4. Senate and bicameral records when obtainable
5. Final General Appropriations Act
6. DBM allotment, obligation and disbursement reports
7. DPWH procurement and implementation records
8. PhilGEPS awards
9. PCAB contractor verification
10. COA findings

Every acquired artifact records its source, retrieval time, SHA-256 digest,
media type, byte size and source classification. Original bytes are immutable.

## Publication rules

- Exact links require a shared official identifier or a source document that
  explicitly connects both records.
- High-confidence derived links require a unique combination of normalized
  title, year, location, implementing office, funding source and compatible
  amount.
- Candidate and conflicting links are quarantined.
- A zero or missing downstream amount is never interpreted as proof that no
  funds were released.
- Project-family totals must not be presented as one contract or one physical
  asset unless documentary evidence proves that identity.
- Every red flag publishes the rule, inputs, calculation, confidence and
  source evidence.

## Initial implementation slice

The first slice provides:

- A validated registry of primary and secondary sources
- Content-addressed immutable artifact storage
- Exact peso and centavo normalization without floating-point arithmetic
- Canonical budget-stage and project-link models
- Control-total reconciliation
- Deterministic flags for post-NEP introduction, stage increases, repeated
  funding and inconsistent downstream project data
- Tests for valid, invalid, ambiguous and conflicting records

This foundation does not fetch on a schedule or restore any decommissioned
runtime. Its verified derivatives now feed the separate read-only Busisi
publication service described below.

## Accuracy gates

- Boundary validation rejects malformed years, amounts, URLs and identifiers.
- Every reconciliation result retains the expected, observed and difference
  amounts.
- High-confidence publication requires a reviewed golden set and measured
  precision of at least 95 percent.
- Ambiguous matching never falls back to the highest-scoring candidate.
- Rule changes rerun historical fixtures and report changed classifications.
- Source artifacts remain reproducible from their manifest and digest.

## Implementation status

As of 2026-11-03:

- The initial source, archive, normalization, reconciliation, matching and
  red-flag foundation is implemented.
- A local canonical SQLite store persists immutable source snapshots and
  explicit pagination checkpoints. It is isolated from the publication
  database and is never queried by a public request.
- GAA program ingestion supports opaque cursor resumption with 500 records per
  page. DPWH project ingestion supports numbered-page resumption with 1,000
  records per page.
- Zero-value GAA placeholders are retained in the source artifact but excluded
  from positive-funding canonical records.
- Project-family identities remove phase and completion markers while retaining
  asset type and location evidence.
- BetterGov's GAA Parquet `amt` values are stored in thousands of pesos. The
  importer declares the 1,000 multiplier explicitly and reconciles normalized
  totals against the API before publication.
- The reviewed linkage set contains 6 of the required 100 cases. Five are
  published as reviewed dossiers and one unresolved FY2026 case is published
  with `noindex` as a quarantined example. The 100-case gate continues to block
  automatic publication of inferred cross-source links. It does not block
  direct publication of official source records with clear labels.
- Repeat-funding evaluation aggregates separate phases within a fiscal year and
  requires positive funding in at least two distinct fiscal years.
- The public identity is **Busisi** with a documented public-records design
  system. The responsive interface exposes overview, explorer, review signals,
  methodology and evidence dossiers. See `docs/busisi-design-system.md`.
- The production Cloudflare Worker uses D1 for indexed server-side search,
  cursor pagination and reviewed dossier lookup. It publishes 68,608 positive
  GAA records, 56,887 DPWH delivery records and 385 explicitly unreviewed
  candidate links from archived FY2024 to FY2026 snapshots.
- The FY2027 change ledger publishes 20,431 source comparisons across four
  program datasets. All rows reconcile to dataset record and monetary control
  totals. 426 held or scope-review DPWH rows remain visibly quarantined.
- The FY2027 appropriation-head ledger publishes 39 national heads and five
  Congress institution children. The 38 House-comparable heads reconcile to
  the bill's printed ₱4.606066495 trillion control. Automatic Appropriations
  remain not applicable to the House bill comparison, not zero.
- The FY2026 allotment-release ledger publishes 96 official DBM rows as of
  30 September 2026: 36 departments, 47 attached agencies or subunits, and 13
  Special Purpose Funds. The retained workbook is SHA-256 pinned, its
  thousand-peso values are normalized to integer centavos, and both current
  GAA and all-source program, release and balance controls reconcile exactly.
  These are not project-level, obligation, disbursement or payment records.
- The deterministic review desk exposes 6,954 House-only rows, 1,784 NEP-only
  rows, 243 increases and 265 decreases. Conservative family normalization
  yields 953 prior-year family candidates and 395 similar-family candidates
  after short generic labels and unusually long aggregate descriptions are
  excluded. These remain review candidates, not findings.
- Review queues provide source links, document links, exact centavo values,
  concentration aggregates and formula-safe CSV exports. No model produces a
  ranking, identity link or label.
- The project-integrity desk publishes 16,814 rule-specific signals derived
  from 56,887 archived DPWH delivery records. These include source-field
  contradictions, amount questions, coordinate reuse and coverage gaps. They
  are review leads, not findings of wrongdoing.
- Contractor activity covers 4,297 identities after explicit slash-delimited
  joint ventures are split into their recorded parties. It provides separate
  rankings by project count and associated project budget. Joint-project
  amounts repeat for each party because the source does not state award shares.
  Name-only identities are not silently merged.
- The current PCAB regular-license snapshot contains 18,868 rows and 15,065
  unique normalized license numbers. A current lookup is not presented as
  evidence of license status on the award date.
- The concentration view publishes 737 region, province or district-office,
  and category groups with at least 20 projects. Shares use contractor-party
  associations as the disclosed denominator and are screening measures only.
- Congressional district context covers all 254 legislative districts in a
  versioned 20th Congress roster and 199 mapped DPWH offices. It attributes
  35,166 delivery records to a single-district office, retains all possible
  districts for 14,027 records from shared offices, and leaves 7,694 records
  unassigned. It never selects one representative for a shared office and does
  not imply project sponsorship, authorship, control or responsibility.
- Coordinate checks currently cover missing values, broad Philippine bounds,
  exact coordinate reuse and conflicting source location labels. They do not
  claim point-in-polygon validation against administrative boundaries.
- The contract outcome pack compares the three exact procurement matches with
  their DPWH delivery records. It checks amount consistency, completion-state
  conflicts, event order, planned-versus-actual dates, inspection coverage and
  project-specific payment coverage without inferring missing values.
- Three contract rows extracted from a version-pinned BetterGov PhilGEPS mirror
  add secondary awardee and award-amount comparisons. Each row has a canonical
  SHA-256 and source revision. The complete mirror snapshot is archived and
  hashed. Original PhilGEPS award pages are not archived, and mirror rows are
  not represented as official evidence.
- The contract evidence ledger tracks nine lifecycle targets for each of the
  three contracts, or 27 checks in total. One official source artifact is
  archived and verified, three official-source acquisitions are blocked and
  retryable, three rows are retained as secondary mirror evidence and 20 target
  documents have not been located. Reported dates do not satisfy document
  acquisition.
- The full contract detail publication contains 56,887 contract states, 62,129
  accepted exact secondary rows, 83 quarantined source rows and 166 candidate
  relationships. Contract pages expose provenance and conflicts without
  exposing the mutable acquisition queue or reviewer decisions.
- The local quarantine review workspace contains a SQLite review ledger, CSV
  export and responsive HTML desk. It begins with 83 unresolved cases and
  requires archived evidence identity for any recorded decision.
- Source artifact hashes, row counts and monetary control totals reconcile
  exactly between the canonical SQLite store, the generated D1 bundle and the
  remote D1 database.
- The public surface includes canonical URLs, page descriptions, Open Graph
  metadata, JSON-LD, `robots.txt`, `sitemap.xml` and `llms.txt`. It uses no
  model inference, model API, cookies or application analytics.
- IndexNow submission includes every canonical evidence desk, the release
  ledger, public report and contract pages, and five reviewed dossiers. The
  quarantined dossier and public APIs are excluded from indexing.

Run the reviewed-case harness with:

```bash
PYTHONPATH=. python3 ops/harness/budget_watchdog_golden.py
```

Use `--require-release-ready` in a release workflow. It exits with status 2
while the reviewed sample is below the release minimum.

Build and validate the local preview with:

```bash
PYTHONPATH=. python3 ops/harness/budget_watchdog_site.py
```

The route harness requires every rendered page to include a mobile viewport,
a main landmark and resolvable internal links. Its default output remains under
the gitignored `data/budget_watchdog/site-preview/` directory.

Build and verify the isolated reviewed publication database with:

```bash
PYTHONPATH=. python3 ops/harness/budget_watchdog_publication.py
```

Pass `--serve` to expose the local read-only API on loopback port 8766. It
provides indexed project search, reviewed/quarantine and fiscal-year filters,
stable cursor pagination, deterministic sorting, dossier lookup and filtered
server-generated CSV. The publication database contains only reviewed golden
fixtures and is derived separately from the canonical ingestion database.

Build and verify the Cloudflare asset and D1 seed bundle with:

```bash
PYTHONPATH=. python3 ops/harness/budget_watchdog_cloudflare.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_public_data.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_pcab.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_districts.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_integrity.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_agencies.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_allotment_releases.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_public_value.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_coa.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_procurement.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_contract_evidence.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_acquisition_release.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_acquisition_universe.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_acquisition_retry.py --limit 10
PYTHONPATH=. python3 ops/harness/budget_watchdog_source_monitor.py
cd cloudflare/busisi
npm test
npm run check
```

The reviewed seed and static assets are generated under the gitignored
`data/budget_watchdog/cloudflare-preview/` directory. The source-record bundle
is generated under `data/budget_watchdog/public-d1-bundle/`, verified in an
in-memory database and split into manifest-hashed import chunks. The stage
comparison bundle is built under `data/budget_watchdog/hgab-d1-bundle/` and
uses the same verification contract. The appropriation-head bundle is built
under `data/budget_watchdog/agency-d1-bundle/`, with its source snapshot under
`data/budget_watchdog/agency-2027-snapshot/`. The allotment-release bundle is
built under `data/budget_watchdog/allotment-release-d1-bundle/` from the retained
snapshot under `data/budget_watchdog/allotment-release-2026-snapshot/`. Its parser
checks the XLSX container, source origin, digest, fiscal date, hierarchy and
exact monetary controls before emitting SQL. The delivery-integrity bundle is built
under `data/budget_watchdog/integrity-d1-bundle/`, hashes every import chunk and
verifies the generated SQL in an isolated SQLite database. The public-value
bundle is built under `data/budget_watchdog/public-value-d1-bundle/` from the
official DBM BESF Tables A.1 and A.2 snapshot under
`data/budget_watchdog/public-value-2027-snapshot/`. The reviewed COA evidence
bundle is built under `data/budget_watchdog/coa-d1-bundle/`; it keeps report
discovery, archived copies and project-level observation matches as separate
states. The contract evidence bundle is built under
`data/budget_watchdog/contract-evidence-d1-bundle/`; it validates complete
nine-stage checklists and verifies the generated SQL in an isolated database.
The acquisition-universe release is built under
`data/budget_watchdog/acquisition-universe-d1-bundle/`. Its frozen catalogue
reconciles 56,887 contracts, 511,983 lifecycle tasks, match states, queue states,
fiscal years, category groups and both source fingerprints. The full 5,481,161
row mirror, per-contract scan and mutable acquisition queue remain local and
are never bound to the Worker. `ops/systemd/busisi-acquisition-retry.timer`
runs the bounded official-source retry harness daily on the data host.
`ops/systemd/busisi-project-image-coverage.timer` runs the gated image-evidence
queue every six hours. It uses a 25-contract canary, 100-contract chunks, four
worker-local HTTP sessions and a shared two-request-per-second host limiter.
The adaptive controller begins at 1,000 contracts per cycle, ramps to 2,000
after eight healthy cycles, and reduces work after retryable source failures.
Two rate limits or a retryable failure ratio above 10 percent halt the cycle
before publication. Permanent HTTP access failures are recorded as blocked
coverage gaps rather than repeatedly requested.
The queue selection is deterministic and mixes fiscal years and source image
hints. Publication remains limited to reconciled metadata and inspected JPEG
artifacts; conflicts remain quarantined.
`npm run check`
enforces at least 95
percent Worker line and function coverage and at least 90 percent branch
coverage, then performs Wrangler dry runs. Verify the production deployment
independently
with:

```bash
cd cloudflare/busisi
npm run verify:live
npm run submit:indexnow
```

The live harness verifies DNS, HTTPS, canonical metadata, discovery files,
security headers, exact dataset counts, artifact hashes, representative source
queries, reviewed and quarantined dossier boundaries, redirects and assets.
The credential-free GitHub production monitor runs this contract every six
hours from `.github/workflows/busisi-production-monitor.yml`. Monitoring is
read-only and cannot deploy or mutate D1.

`.github/workflows/source-drift-monitor.yml` independently checks source
revisions and catalogues every six hours and retains the archived responses and
report for 30 days. `ops/systemd/busisi-operational-audit.timer` performs the
same source check on the data host, publishes the status to the read-only public
API, and then checks queue integrity, expired leases, publication markers,
existing acquisition timers and the live production contract. A changed or
unavailable source produces a nonzero result and is not published as replacement
data. The monitored baseline is reviewed and versioned at
`ops/harness/fixtures/source_monitor_baseline.json`.

The public status endpoint is `/api/v1/source-monitor-status`; `/coverage/`
renders the same status for readers. A passing status expires after eight hours
in the live verifier. COA catalogue discovery is listed as a known limitation
because its official catalogue currently blocks unattended acquisition.

The first stable local baseline and its limitations are recorded in
`docs/data-snapshots/2026-11-02-budget-watchdog.md`.
