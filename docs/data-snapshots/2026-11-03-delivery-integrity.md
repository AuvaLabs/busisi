# DPWH delivery-integrity snapshot

Generated and verified on 2026-11-03.

## Scope

This release examines 56,887 DPWH delivery records for fiscal years 2024 to
2026 from the immutable BetterGov DPWH Parquet snapshot. The source reported a
last-modified date of 2026-01-22.

- Source artifact SHA-256: `5b411cf3f112fabd1913c70681791e5e2b78b43a8393f489f48bd882f154e123`
- Integrity bundle manifest SHA-256: `cea59e05113d0b2a4e432d7963540c3238a577d7c9eb339e4ccbd82014f9045c`
- Generated SQL chunks: 14
- Contractor identities: 4,297
- Rule-specific review signals: 16,814
- Contractor concentration groups: 737
- PCAB regular-license rows: 18,868
- PCAB snapshot SHA-256: `016bc9e3427b55e7744558f7726eb773f02f496f88279987c473546d6edb97d2`

The bundle loads into an isolated SQLite database and passes
`PRAGMA integrity_check`. Every public signal retains the source artifact hash.

## Deterministic review rules

| Rule | Signals | Classification |
|---|---:|---|
| Ongoing status with at least 100 percent progress | 5,744 | Source conflict |
| Completed status below 100 percent progress | 7 | Source conflict |
| Start date after completion date | 1 | Source conflict |
| Nonpositive budget after procurement | 23 | Amount review |
| Coordinate not available | 7,771 | Coverage gap |
| Completed without a source satellite image | 2,029 | Coverage gap |
| Exact coordinate reused across distinct project descriptions | 1,230 | Identity review |
| Exact coordinate paired with conflicting source location labels | 5 | Source conflict |
| Same coordinate and normalized project family across fiscal years | 4 | Identity review |

No selected record fell outside the current broad Philippine latitude and
longitude screening bounds. This is not administrative-boundary validation.

One contract can meet more than one rule, so the signal total is not a count of
unique suspect projects. The release does not combine these rules into a risk
or corruption score.

## Contractor aggregation

Explicit slash-delimited joint ventures are split into their recorded parties.
Contractors are grouped by the PCAB identifier recorded as a numeric suffix in
each party. When no PCAB identifier is present, a normalized name digest is
used without merging it into a PCAB identity. The public view offers two
independent rankings:

1. Number of archived project records
2. Sum of associated project budgets in integer centavos

The aggregation also reports completed, ongoing and terminated source-status
counts and the first and last fiscal year present. Joint-project amounts repeat
for each recorded party because the source does not state the individual award
share. A high count or budget total does not establish concentration abuse,
poor performance or unlawful conduct.

The PCAB check uses a 2026-11-03 snapshot of the official current regular-license
table. Of the 4,297 contractor identities, 3,788 match a current regular license
marked for government infrastructure, 9 match a current regular license not so
marked, 490 recorded PCAB identifiers are not found in that current table, and
10 name-only identities cannot be checked. These are current lookup results,
not historical license findings for the award date.

The 737 concentration rows cover source region labels, province or district-
office labels, and project categories with at least 20 records. The share is
the leading party's project associations divided by all contractor-party
associations in the group. It is not a market-share or award-share estimate.

## Limitations

- The source is an archived snapshot, not a current DPWH operational feed.
- Status, progress, imagery and coordinates can update on different schedules.
- Missing coordinates or imagery are coverage gaps and do not indicate a
  missing physical project.
- Exact coordinate reuse can reflect a shared facility, representative point,
  office centroid or repeated source entry.
- Conflicting source location labels do not prove that a coordinate is outside
  the correct administrative boundary.
- Point-in-polygon checking is withheld until an authoritative, licensed and
  versioned administrative-boundary artifact is registered and archived.
- PCAB verification reflects the current regular-license table and cannot prove
  license status at the time a contract was awarded.
- PhilGEPS contract-level linkage is not published because a complete,
  reproducible award artifact has not yet been acquired.
- Budget and implementation records alone cannot establish fraud, corruption,
  a ghost project, procurement collusion or political authorship.
