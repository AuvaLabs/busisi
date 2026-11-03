# Busisi publication snapshot, 2026-11-03

## Deployment

- Origin: `https://busisi.org`
- Worker: `busisi-publication`
- Worker version: `67ef049a-3b36-4208-af36-363c4be70287`
- D1 database: `busisi-publication`
- D1 database ID: `506a96f9-03a3-47f5-8f86-dd3b6c7d1f2c`
- D1 region: Western Europe

The deployed Worker has D1, static asset and rate-limit bindings. It has no AI
or model binding and performs no model inference.

## Reconciled public data

| Collection | Records | Monetary control total |
|---|---:|---:|
| Positive GAA appropriations | 68,608 | ₱2,617,581,913,000.00 |
| DPWH delivery records | 56,887 | ₱1,852,028,127,050.82 |
| Unreviewed candidate links | 385 | Not aggregated as findings |
| Reviewed dossiers | 5 | Per-record comparison only |
| Quarantined dossier examples | 1 | Per-record comparison only |

The remote D1 counts and monetary totals match the canonical SQLite source
exactly. The canonical SQLite integrity check returned `ok`.

## Artifact identity

- GAA artifact SHA-256: `6ed63d8db36e10280782ff2c9e5e1c32fe99ffbe2ff0accfe319a025203a48c4`
- DPWH artifact SHA-256: `5b411cf3f112fabd1913c70681791e5e2b78b43a8393f489f48bd882f154e123`
- Public D1 manifest SHA-256: `edf802d5cfcd764cdcea6c8fa2a3210132692c106cd4becd86def578bef4c5e9`
- Reviewed seed SHA-256: `3f59f5100cd5bbe7cb64e80142ab6ff52faae70dc34b2fbf18c3ea829ce5bcf0`

All 66 D1 import chunks matched their manifest hashes before upload.

## Publication boundary

- Official source records are searchable as records, not findings.
- Candidate links are visibly marked unreviewed.
- Five reviewed dossiers are indexable.
- The unresolved FY2026 dossier is quarantined and `noindex`.
- Insertion analysis remains unavailable until stage-by-stage budget records
  are acquired.
- Physical existence cannot be established from budget data alone.
- The 100-case accuracy gate remains in force for automatic publication of
  inferred cross-source links.

The live harness passed DNS, HTTPS, page, API, count, artifact hash, dossier,
redirect, asset and security-header checks. IndexNow accepted the four canonical
pages and five reviewed dossiers with HTTP 200.

## Unattended verification

The `Busisi production monitor` GitHub workflow runs the live contract every
six hours and can also be triggered manually. It has read-only repository
permissions, contains no secrets and has no deployment or database mutation
step. A changed count, changed artifact hash, unavailable route, unexpected
index state or failed representative query causes the workflow to fail.

The private source repository was reopened so these workflows can run. The
unrelated retired deployment and publication workloads remain decommissioned.
