# DPWH delivery-integrity snapshot

Generated and verified on 2026-11-03.

## Scope

This release examines 56,887 DPWH delivery records for fiscal years 2024 to
2026 from the immutable BetterGov DPWH Parquet snapshot. The source reported a
last-modified date of 2026-01-22.

- Source artifact SHA-256: `5b411cf3f112fabd1913c70681791e5e2b78b43a8393f489f48bd882f154e123`
- Integrity bundle manifest SHA-256: `3ea4adbcd0e87bea3b6d547ca864a640ab061a26b4c64ca2c3db04318c45b39e`
- Generated SQL chunks: 44
- Contractor identities: 4,297
- Rule-specific review signals: 16,814
- Contractor concentration groups: 737
- PCAB regular-license rows: 18,853
- PCAB snapshot SHA-256: `e3ed711707a5c2e52efe907148d59b39a028b78fa0458d840250dad977362fa1`
- Legislative districts in the roster snapshot: 254
- Mapped DPWH offices: 199
- District snapshot SHA-256: `dc78c26838c81da134e2ae7523a45f0bd7792d2a01e06f6694fc351a25650e46`

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
table. Of the 4,297 contractor identities, 3,789 match a current regular license
marked for government infrastructure, 9 match a current regular license not so
marked, 489 recorded PCAB identifiers are not found in that current table, and
10 name-only identities cannot be checked. These are current lookup results,
not historical license findings for the award date.

The 737 concentration rows cover source region labels, province or district-
office labels, and project categories with at least 20 records. The share is
the leading party's project associations divided by all contractor-party
associations in the group. It is not a market-share or award-share estimate.

## Congressional district context

District context uses a versioned BetterGov 20th Congress district snapshot
at source commit `a0caa778442cdae5583f5a006ea7401dab00e5ac`, retrieved
on 2026-11-03. Representative records link to the corresponding official House
member profile when one is available. The two acquired API pages retain their
original bytes and SHA-256 digests:

- `df266f4eb6ab1ecda56a6a30b48130d7597fa2d59a455a4abf36e925222fe808`
- `95f660d853867c809a24eaf719820e7e0e14084817ebdd32f27e4973fb11672b`

The mapping is deliberately office-based, not coordinate-based. An exact DPWH
office that serves one district provides a single-district context. An office
that serves several districts publishes every listed district and
representative without selecting one. Offices with no exact mapping remain
unassigned.

| Attribution | Delivery records |
|---|---:|
| Single-district office | 35,166 |
| Shared office, all districts retained | 14,027 |
| Unassigned | 7,694 |

This context does not identify who requested, sponsored, controlled, inserted,
or is responsible for a project or budget amount. Two district seats have an
ambiguous representative roster entry; both names and the ambiguity note are
retained rather than choosing one.

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
- District context follows the listed DPWH office and must not be read as a
  project coordinate falling inside a legislative boundary.
- PCAB verification reflects the current regular-license table and cannot prove
  license status at the time a contract was awarded.
- PhilGEPS contract-level linkage is not published because a complete,
  reproducible award artifact has not yet been acquired.
- Budget and implementation records alone cannot establish fraud, corruption,
  a ghost project, procurement collusion or political authorship.
