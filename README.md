# Busisi

Busisi is an evidence-first explorer for Philippine public budget and delivery
records. It publishes official source records, deterministic review signals,
an FY2027 NEP-to-House project ledger, a national appropriation-head ledger,
an FY2027 source-separated budget publication trail, a reconciled FY2026
allotment-release ledger, and a small reviewed dossier set
without using a language model. A separate COA evidence layer records which official
audit catalogues were checked, whether source bytes were acquired, and whether a
project-level observation was actually matched. Contract outcome cross-checks
compare exact procurement records with the DPWH delivery snapshot while keeping
award, awardee, inspection and payment evidence states explicit. A complete
version-pinned BetterGov PhilGEPS mirror snapshot is archived with its original
bytes and SHA-256. It remains secondary evidence and is never labelled an
official award notice.
For three reviewed contracts, a separate acquisition ledger tracks nine target
documents from procurement planning through payment. Each target is classified
as archived official evidence, an indexed but unarchived source, a blocked
acquisition, secondary mirror evidence or a document not located. A date
reported in a monitoring row never substitutes for the underlying document.

The acquisition universe covers all 56,887 FY2024 to FY2026 DPWH delivery
contracts. The deterministic scan found usable exact secondary rows for 47,071
contracts, no exact mirror row for 9,655, and conflicting exact identifiers for
161. It retained 62,129 exact rows, quarantined 83 conflicting source rows, and
created 511,983 lifecycle tasks. The canonical queue stays local. Read-only
contract states, exact secondary rows, quarantined conflicts, reconciled
counts, source identity and limitations are published to D1. Every contract
has a human-readable drill-down. Review decisions and the mutable queue remain
local.

The public review desk ranks stage changes, groups monetary movement by region,
office, program or dataset, identifies conservative cross-year project-family
candidates, and exports source-linked CSV evidence.

The project-integrity desk publishes deterministic DPWH source contradictions,
coordinate review signals and coverage gaps. Its contractor view separately
ranks archived activity by project count and total project budget. Neither view
uses a model or produces a corruption score.

Where the listed DPWH office has an exact roster mapping, records also show the
roster-snapshot congressional district and representative. Shared offices retain every
possible district, and unmatched offices remain unassigned. This context does
not imply project sponsorship, control or responsibility.

Production: [busisi.org](https://busisi.org)

## Accuracy contract

The publication pipeline follows this order:

1. Acquire and hash official source artifacts.
2. Archive original bytes and record provenance.
3. Validate schemas and fiscal years.
4. Normalize monetary values as integer centavos.
5. Reconcile control totals.
6. Match identities using deterministic evidence.
7. Classify confidence and calculate review signals.
8. Quarantine ambiguous links.
9. Publish read-only records with sources and limitations.

A signal identifies a record for further review. It is not a finding of
wrongdoing. Inferred links do not publish automatically until the reviewed
golden set reaches the documented precision gate.

## Repository layout

| Path | Purpose |
|---|---|
| `engine/budget_watchdog/` | Acquisition, archive, validation, normalization, matching, signals and publication builders |
| `engine/tests/budget_watchdog/` | Unit and integration tests |
| `ops/harness/` | Deterministic data, site and publication verification commands |
| `cloudflare/busisi/` | Production Worker, D1 schema, public interface and live verifier |
| `docs/` | Build contract, design system and dated data snapshots |

## Verify locally

```bash
python -m pip install -r requirements-dev.txt
PYTHONPATH=. pytest engine/tests/budget_watchdog -q
PYTHONPATH=. python3 ops/harness/budget_watchdog_golden.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_hgab.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_agencies.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_allotment_releases.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_districts.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_integrity.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_senate.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_senate_monitor.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_coa.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_contract_evidence.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_acquisition_release.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_acquisition_universe.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_acquisition_retry.py --limit 10
cd cloudflare/busisi
npm ci
npm run check
npm run verify:live
```

Generated data and local publication bundles are written under
`data/budget_watchdog/` and are not committed.

## Runtime

The public service is a read-only Cloudflare Worker backed by an isolated D1
publication database. The canonical acquisition database is never bound to a
public request. The publication database contains derived read-only evidence,
never the local review queue or reviewer decisions. Production monitoring is
credential-free and read-only.
The Senate catalogue monitor runs every six hours, preserves its bounded source
responses as workflow evidence, and fails closed when records change or source
acquisition becomes unreliable. It never updates the reviewed baseline
automatically.

The local acquisition retry timer runs one bounded batch daily. It accepts only
registered official DPWH HTTPS origins, archives successful source bytes, uses
exponential backoff for retryable HTTP failures, and blocks a task after the
configured attempt limit for review.

## License

Proprietary.
