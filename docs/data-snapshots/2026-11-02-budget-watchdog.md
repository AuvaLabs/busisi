# Budget watchdog baseline snapshot, 2026-11-02

## Purpose

This is a local development baseline for the Philippine budget watchdog. It is
not approved for public release because the DPWH delivery snapshot is dated and
the reviewed linkage set has not reached its minimum size.

This statement records the 2026-11-02 decision boundary. On 2026-11-03, the
official source records were published with their snapshot dates and explicit
limitations. The 100-case minimum still applies to automatic publication of
inferred cross-source links. See `2026-11-03-busisi-publication.md` for the
production reconciliation record.

## Source artifacts

| Dataset | Source version | Source modified | Bytes | SHA-256 |
|---|---|---:|---:|---|
| BetterGov GAA Parquet | `84d0a6b87122fd6e8302cbc17c86feee7ef5d8b3` | 2026-01-29 | 79,707,700 | `6ed63d8db36e10280782ff2c9e5e1c32fe99ffbe2ff0accfe319a025203a48c4` |
| BetterGov DPWH Parquet | `648ea96af4f7625d606fda0b78803917913a26b7` | 2026-01-22 | 24,330,129 | `5b411cf3f112fabd1913c70681791e5e2b78b43a8393f489f48bd882f154e123` |

Both archived blobs were re-hashed after storage and matched their published
digests.

## Canonical records

| Fiscal year | Positive GAA program families | GAA amount | DPWH contracts | DPWH project budgets |
|---|---:|---:|---:|---:|
| 2024 | 24,927 | ₱997,884,938,000 | 30,569 | ₱1,059,299,931,428.91 |
| 2025 | 25,521 | ₱1,088,800,308,000 | 26,051 | ₱792,728,195,621.91 |
| 2026 | 18,160 | ₱530,896,667,000 | 267 | ₱0 |

The GAA Parquet source stores `amt` in thousands of pesos. Applying a 1,000
source-unit multiplier produced exact 2024 and 2025 API control totals.

The 2026 canonical sum excludes one quarantined source row whose description is
only `-`. Its ₱2,194,000 amount is retained in quarantine. Adding that amount
produces the exact ₱530,898,861,000 API control total.

## Quarantine

| Code | Rows | Amount | Reason |
|---|---:|---:|---|
| `invalid_gaa_row` | 1 | ₱2,194,000 | Description has no canonical project identity |

Quarantined money remains in reconciliation controls but is not assigned to a
project family or published as a named project.

## Verified project-family example

The deterministic family normalizer grouped these separate contracts under
`construction of multi purpose building barangay corazon catmon cebu`:

- `24HI0148`, Phase 1
- `24HI0131`, Phase 2
- `25HI0028`, completion

The family relationship does not assert that every contract is the same
physical structure. Contract identities and amounts remain separate.

## Limitations and release blockers

- The DPWH snapshot was last modified on 2026-01-22. It contains only 267 FY2026
  records, all with zero project budgets, while the live API is materially
  newer.
- Live numbered pagination can move while a crawl is running. A live delta must
  record start and end totals and quarantine the run if those controls change.
- The reviewed linkage set contains 6 cases. The release minimum is 100 with at
  least 95 percent agreement for automatically published high-confidence links.
- At this baseline, no public record API, record interface, schedule or
  production database was active. The 2026-11-03 publication snapshot
  supersedes that deployment state while retaining the same evidence limits.
