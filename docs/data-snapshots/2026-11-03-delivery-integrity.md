# DPWH delivery-integrity snapshot

Generated and verified on 2026-11-03.

## Scope

This release examines 56,887 DPWH delivery records for fiscal years 2024 to
2026 from the immutable BetterGov DPWH Parquet snapshot. The source reported a
last-modified date of 2026-01-22.

- Source artifact SHA-256: `5b411cf3f112fabd1913c70681791e5e2b78b43a8393f489f48bd882f154e123`
- Integrity bundle manifest SHA-256: `32370f611e808a5c67d69a1e1bcf05a20f93c8c8ee655223db7f298513feadf2`
- Generated SQL chunks: 13
- Contractor identities: 4,274
- Rule-specific review signals: 16,810

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

No selected record fell outside the current broad Philippine latitude and
longitude screening bounds. This is not administrative-boundary validation.

One contract can meet more than one rule, so the signal total is not a count of
unique suspect projects. The release does not combine these rules into a risk
or corruption score.

## Contractor aggregation

Contractors are grouped by the PCAB identifier recorded as a numeric suffix in
the source contractor field. When no PCAB identifier is present, a normalized
name digest is used without merging it into a PCAB identity. The public view
offers two independent rankings:

1. Number of archived project records
2. Sum of recorded project budgets in integer centavos

The aggregation also reports completed, ongoing and terminated source-status
counts and the first and last fiscal year present. A high count or budget total
does not establish concentration abuse, poor performance or unlawful conduct.

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
- Contractor names and PCAB identifiers reproduce the source fields. Current
  registration status must be checked against the PCAB verification service.
- Budget and implementation records alone cannot establish fraud, corruption,
  a ghost project, procurement collusion or political authorship.
