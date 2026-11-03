# Busisi strategy

## Purpose

Busisi helps journalists, researchers and citizens trace Philippine budget
records across fiscal years and delivery datasets. The product makes public
records easier to search, compare and verify while preserving a direct path to
the source evidence.

## Current release

The production explorer publishes official GAA and DPWH records, explicitly
unreviewed candidate links, five reviewed dossiers and one quarantined example.
It also publishes 20,431 provisional FY2027 comparisons between NEP and House
bill project lists across DPWH, farm-to-market roads, health facilities and
irrigation. The service has no model dependency. Deterministic rules generate
review signals, and every public signal includes its inputs and limitations.
The review desk turns those comparisons into source-linked queues for House-only
rows, increases, decreases, removals, prior-year project families and similar
FY2027 family labels. It also publishes regional, office, program and dataset
concentrations and CSV evidence exports.

The project-integrity desk adds deterministic review of the archived DPWH
delivery snapshot. It publishes source-field contradictions, coverage gaps,
coordinate reuse and source-location conflicts with the evidence and limitation
beside each result. A separate contractor view ranks 4,297 identities by
project count or associated project budget after splitting explicit
slash-delimited joint ventures. Current PCAB lookup status and transparent
contractor-party concentration shares are published with their limitations.
Neither view produces a composite risk score or infers wrongdoing.

The FY2027 publication trail separately catalogs the Senate Budget
Transparency Portal. Four portal records are classified as House bill volumes
because their titles identify HB 10858 at third reading, and one record is
classified as supporting fiscal analysis. Two archived mirror copies pass
their recorded SHA-256 checks. Senate committee, Senate amendment, bicameral,
and enacted GAA stages remain explicitly unavailable rather than being inferred
from the portal's fiscal-year label.

The contract outcome pack cross-checks exact procurement evidence against the
DPWH delivery snapshot. It compares contract amounts, procurement and delivery
states, planned and actual events, implementation dates, inspection coverage
and project-specific payment coverage. A discrepancy is a documentary-review
question, not a finding. Contractor names from delivery records are not treated
as independently verified awardees. Three version-pinned BetterGov PhilGEPS
mirror rows support secondary awardee and amount cross-checks. Their source
revision and row hashes are retained. The complete source snapshot is archived,
while original official award pages remain explicitly unarchived.

The contract evidence acquisition ledger makes the next documentary step
visible for each of those contracts. It tracks nine lifecycle targets per
contract and keeps source availability separate from evidentiary strength. The
current 27 checks include one archived official artifact, three blocked
official-source acquisitions, three secondary mirror rows and 20 documents not
located. Missing inspection, acceptance or payment documents remain evidence
gaps, not evidence that the event did or did not occur.

The full-universe acquisition engine extends that evidence model to every
FY2024 to FY2026 DPWH delivery contract. It archives and hashes the complete
version-pinned secondary mirror, validates all 56,887 identifiers, preserves 97
contract-year alignment conflicts as source conflicts, and quarantines 83 rows
whose exact identifiers point to more than one contract. It does not select one
row automatically when multiple exact rows exist. The 511,983-stage local queue
is resumable and leased; its public release contains reconciled summaries only.

Project and change records also show congressional district context when the
listed DPWH office can be matched exactly. A single-district office names that
district and its representative as recorded in the dated roster snapshot. Shared offices show every served
district and representative, while unmatched offices stay unassigned. This is
office context, not coordinate-based boundary validation, political authorship
or evidence that a representative requested or controls the project.

## Release gates

| Area | Gate |
|---|---|
| Acquisition | Source is registered, bounded and archived with a SHA-256 digest |
| Normalization | Schema, year, unit and monetary validation pass |
| Reconciliation | Expected and observed control totals agree or the artifact is quarantined |
| Identity | Exact evidence or a reviewed high-confidence match exists |
| Signals | Rule, inputs, confidence and limitations are publishable |
| Inferred links | At least 100 reviewed cases and at least 95 percent measured precision |
| Deployment | Python tests, Worker coverage, bundle checks and live contract all pass |

## Next practical work

1. Review and label representative candidates from each deterministic FY2027
   queue without treating queue position as a risk score.
2. Expand the cross-source reviewed golden set from 6 to 100 cases.
3. Refresh the FY2027 publication catalogue and extend the comparison ledger
   when stable Senate, bicameral and final GAA artifacts can be acquired and
   reconciled.
4. Continue the bounded official-source retry runner and acquire award notices,
   signed contracts, completion certificates, inspection and acceptance
   records, payment records and COA findings only when reproducible official
   artifacts can be retained and their identifier limitations modeled.
5. Register an authoritative, reusable administrative-boundary artifact before
   adding point-in-polygon coordinate validation. Until then, keep exact source
   coordinate checks visibly separate from geographic verification.
6. Review high-volume name-only contractor identities and quarantine ambiguous
   mergers instead of collapsing similar business names.
7. Add alerts for source drift and publication mismatch without granting the
   monitor deployment or database mutation credentials.
8. Reconcile district and representative changes against a newly archived
   roster snapshot before updating public names, keeping prior snapshot hashes.

## Decision rules

- Do not claim that a budget signal proves corruption, insertion or a ghost
  project.
- Do not equate a missing downstream amount with zero release or zero delivery.
- Do not merge separate phases into one physical asset without documentary
  evidence.
- Do not use a model to bridge missing evidence.
- Do not assign a project to one representative when its DPWH office serves
  several districts.
- Prefer a smaller verified publication over a larger uncertain one.

Last updated: 2026-11-03.
