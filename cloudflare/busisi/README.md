# Busisi Cloudflare publication

This package contains the production Worker, D1 publication schema, static
assets, tests and the read-only live verification contract for busisi.org.

D1 stores publication records only. The canonical acquisition database is
never bound to the Worker.

## Local checks

```bash
npm ci
npm test
npm run check
```

`npm run check` builds deterministic publication bundles, enforces at least 95
percent line and function coverage and 90 percent branch coverage, and performs
a Wrangler dry run.

The COA bundle keeps report discovery, archived source copies, agency or program
context, and reviewed project-observation matches as separate states. A missing
match is never presented as audit clearance.

The contract outcome endpoint derives read-only cross-checks from exact
procurement evidence, version-pinned secondary PhilGEPS mirror rows, and the
DPWH delivery snapshot. Mirror awardees and amounts stay visibly secondary
because the mirror is not an official award notice. It
does not infer inspection, payment, or audit results from a contractor name or
status.

The contract evidence endpoint publishes 27 lifecycle acquisition checks for
three reviewed contracts. The checklist covers procurement plan, bid notice,
procurement monitoring report, award notice, signed contract, Notice to
Proceed, completion certificate, inspection and acceptance, and payment
record. One original official artifact is archived and verified, three
official-source acquisitions are blocked and retryable, three extracted rows
are secondary evidence, and 20 target documents have not been located. Reported
dates remain separate from document acquisition.

The acquisition coverage endpoint publishes reconciled summary controls for
all 56,887 FY2024 to FY2026 DPWH contracts. It exposes match-state, fiscal-year,
category and queue totals, plus the archived mirror fingerprint. It does not
expose the local queue database or individual secondary rows. Current controls
are 47,071 contracts with usable exact secondary rows, 9,655 with no exact row,
161 quarantined identifier conflicts, and 83 conflicting source rows.

The contract intelligence explorer at `/contracts/` makes that full publication
universe searchable by fiscal year, place, category, delivery status, budget,
contractor, acquisition state and deterministic review coverage. Readers can
compare up to three records and export the same filtered evidence as CSV. Exact
secondary rows remain labelled as discovery evidence, conflicts remain
quarantined, and missing evidence is never presented as clearance.

The allotment-release ledger at `/releases/` publishes 96 official FY2026 DBM
department, attached-agency, subunit and Special Purpose Fund records as of
30 September 2026. Current GAA and all-source controls reconcile exactly after
converting the workbook's thousand-peso values to integer centavos. Allotment
release remains separate from obligation, disbursement and payment evidence.

## Production verification

```bash
npm run verify:live
npm run submit:indexnow
```

The live verifier checks DNS, HTTPS, canonical metadata, discovery files,
security headers, exact dataset counts, artifact hashes, representative source
queries, stage-change controls, deterministic review-queue counts, evidence CSV,
reviewed and quarantined dossier boundaries, redirects and assets.
It also checks the full-universe acquisition counts, queue controls and source
SHA-256 published at `/api/v1/acquisition-coverage`. Contract explorer checks
cover the full state reconciliation, representative exact and conflict filters,
CSV export and the interactive page assets.
The verifier also checks the release snapshot fingerprint, six monetary control
totals, hierarchy counts and a representative DPWH row.

Deployment and D1 mutation require operator credentials. The scheduled GitHub
monitor is credential-free and read-only.
