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
beside each result. A separate contractor view ranks 4,274 recorded identities
by project count or total project budget. Neither view produces a composite
risk score or infers wrongdoing.

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
3. Extend the FY2027 ledger to Senate, bicameral and final GAA stages when
   stable source artifacts can be acquired and reconciled.
4. Add PhilGEPS awards, PCAB registration status and COA findings only after
   their identifiers and source limitations are modeled explicitly.
5. Register an authoritative, reusable administrative-boundary artifact before
   adding point-in-polygon coordinate validation. Until then, keep exact source
   coordinate checks visibly separate from geographic verification.
6. Review high-volume name-only contractor identities and quarantine ambiguous
   mergers instead of collapsing similar business names.
7. Add alerts for source drift and publication mismatch without granting the
   monitor deployment or database mutation credentials.

## Decision rules

- Do not claim that a budget signal proves corruption, insertion or a ghost
  project.
- Do not equate a missing downstream amount with zero release or zero delivery.
- Do not merge separate phases into one physical asset without documentary
  evidence.
- Do not use a model to bridge missing evidence.
- Prefer a smaller verified publication over a larger uncertain one.

Last updated: 2026-11-03.
