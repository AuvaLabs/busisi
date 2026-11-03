# Busisi

Busisi is an evidence-first explorer for Philippine public budget and delivery
records. It publishes official source records, deterministic review signals,
an FY2027 NEP-to-House project ledger, a national appropriation-head ledger,
an FY2027 source-separated budget publication trail, and a small reviewed dossier set
without using a language model. A separate COA evidence layer records which official
audit catalogues were checked, whether source bytes were acquired, and whether a
project-level observation was actually matched.

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
PYTHONPATH=. python3 ops/harness/budget_watchdog_districts.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_integrity.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_senate.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_senate_monitor.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_coa.py
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
public request. Production monitoring is credential-free and read-only.
The Senate catalogue monitor runs every six hours, preserves its bounded source
responses as workflow evidence, and fails closed when records change or source
acquisition becomes unreliable. It never updates the reviewed baseline
automatically.

## License

Proprietary.
