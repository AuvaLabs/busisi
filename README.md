# Busisi

Busisi is an evidence-first explorer for Philippine public budget and delivery
records. It publishes official source records, deterministic review signals,
an FY2027 NEP-to-House comparison ledger, and a small reviewed dossier set
without using a language model.

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

## License

Proprietary.
