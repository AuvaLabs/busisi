# Public-services inventory snapshot, 2026-11-04

## Published scope

The public-services inventory classifies acquired record titles, not physical
facilities. It keeps FY2027 budget-stage rows separate from FY2024 to FY2026
DPWH delivery contracts and never adds their money into one investment total.

The current deterministic classification contains:

- 6,050 title-classified records
- 937 budget-stage rows
- 5,113 delivery contracts
- 4,722 school-related records
- 671 hospital records
- 657 health-center records

Work wording is separately classified as 3,611 new-build, 798 rehabilitation,
31 expansion, one equipment, 703 continuation or phase, and 906 unspecified
records. A work type describes title wording. It does not establish that the
named work occurred.

## Facility rules

The `public-services-v2` rules use explicit terms in the acquired title:

- `school`: school or classroom
- `hospital`: hospital, medical center, or medical centre
- `health_center`: health center, health centre, rural health unit, barangay
  health station, infirmary, birthing facility, or an action phrase that ends
  in health facility

The action requirement for the generic `health facility` term prevents a
program heading such as public health facilities from classifying an unrelated
evacuation-center project. Ambiguous names remain outside this inventory.

## Scoped identity pilot

The facility identity layer has four publication states:

- `official_exact`: one official identity passed an exact name and place gate
- `group_only`: records share a normalized label and place, but no official ID
- `ambiguous`: a possible registry name has missing or conflicting place evidence
- `unlinked`: no safe identity or group is available

The first official registry target is the Department of Education's indicative
list of 1,095 possible PPP sites in CAR, NCR, Regions I, II, III, IV-A, IV-B and
V. It is preliminary, non-binding and not a national school registry. The build
requires the original official workbook, archived bytes, SHA-256 provenance, a
reconciled 1,095-row total, unique six-digit school IDs, required identity
fields, valid planning flags and coordinates within broad Philippines bounds.

The official workbook returned HTTP 403 to the unattended acquisition harness
on 2026-11-04. The release therefore remains closed: zero official identities,
zero official record links, zero record groups and zero ambiguous links are
published from this pilot. All 6,050 records remain unlinked. Search-result
renderings and unofficial mirrors are not accepted as substitute source bytes.

When acquisition succeeds, the matcher will examine the 4,722 school-related
records already in the public inventory. It publishes a link only when one
normalized official school name appears in the record title and one compatible
municipality appears in the title or source location. It does not use fuzzy
matching or choose among repeated names.

The release gate is enforced inside the D1 bundle builder. A caller cannot
publish inferred links merely by supplying matcher output. The exact candidate
set and official source artifact must match a reviewed manifest with at least
100 cases, 95 percent measured precision, 95 percent reviewer agreement and no
critical reconciliation failures. Without a passing gate, official registry
rows may be staged after validation, but published record links remain zero.

The public `/api/v1/facility-registry-status` endpoint and the public-services
desk show the latest acquisition and gate state. The scheduled check treats the
known HTTP 403 response as blocked, not as empty data. HTTP 404 or 410, transport
failure, validation failure and a failed review gate require investigation.

## Review flags

Flags remain separated by evidence class:

- stage change
- record contradiction
- location review
- identity conflict
- coverage gap
- repeat family

A row may carry multiple flags. Counts by flag class therefore do not add to
the number of flagged records. A flag is a question for source review and never
a finding of fraud, corruption, a ghost project, or other wrongdoing.

## Evidence limits

The inventory does not establish a unique-facility count, physical existence,
completion, payment, engineering quality, service readiness, beneficiaries, or
measured public value. Every result links to a human-readable budget comparison
or contract evidence page so the source context and limitations can be checked.
