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

1. Expand the reviewed golden set from 6 to 100 cases.
2. Extend the FY2027 ledger to Senate, bicameral and final GAA stages when
   stable source artifacts can be acquired and reconciled.
3. Add PhilGEPS, PCAB and COA evidence only after their identifiers and source
   limitations are modeled explicitly.
4. Publish agency and contractor views after normalization quality supports
   reliable aggregation.
5. Add alerts for source drift and publication mismatch without granting the
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
