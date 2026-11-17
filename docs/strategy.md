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
because their titles identify HB 10858 at third reading, and two records are
classified as supporting fiscal analysis. Two archived mirror copies pass
their recorded SHA-256 checks. Senate committee, Senate amendment, bicameral,
and enacted GAA stages remain explicitly unavailable rather than being inferred
from the portal's fiscal-year label.

The FY2026 allotment-release ledger adds the next verified fiscal stage without
pretending it is payment evidence. It publishes 96 official DBM department,
attached-agency, subunit and Special Purpose Fund records as of 30 September
2026. Every amount is normalized to integer centavos and the current GAA and
all-source controls reconcile exactly. The ledger remains separate from the
FY2027 proposal and legislative comparisons.

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

The gated project-image release dated 16 November 2026 covers 33,155 of 56,890
contracts. Of those records, 10,302 have an exact source-count match, 2,612
report no images in both source views and 20,241 remain source-count conflicts.
The remaining queue contains 14,103 pending records and 9,632 blocked records.
The public release contains 22,541 verified images and holds 191,147 images for
checking. These figures belong to release
`ac5ffd47f7aac897d609472665e285629ee3c4730040d50e6c79f0eca9e2ef63`;
they are a dated snapshot rather than permanent site totals.

Project-image checks run every six hours with bounded work and a source-health
circuit breaker. A count conflict receives one delayed second check after 24
hours. Recoverable access, rate-limit, server and network failures can receive
a delayed check after seven days. Missing records and invalid evidence remain
held. The public coverage page separates all checked records from strongly
resolved records, which are exact matches plus records reporting no images in
both source views.

Project and change records also show congressional district context when the
listed DPWH office can be matched exactly. A single-district office names that
district and its representative as recorded in the dated roster snapshot. Shared offices show every served
district and representative, while unmatched offices stay unassigned. This is
office context, not coordinate-based boundary validation, political authorship
or evidence that a representative requested or controls the project.

A private project-link review workspace now holds a balanced first batch of 120
possible links from the 20,877 high-confidence FY2024 and FY2025 candidate pool.
The batch contains 60 cases per year, 20 per major project type, 30 per project
value band, all 17 recorded regions, 22 joint records, 36 records with an
existing question to check and 119 distinct recorded contractors. Every case
retains the two source links and saved-file check codes. All 120 cases pass the
automated comparison against the saved budget and project records. Each case
still requires two independent decisions. No new link becomes a public reviewed project until at
least 100 cases are checked, at least 95 percent of proposed links are
confirmed, reviewer agreement reaches 95 percent and source totals have no
critical failure.

The private workspace also has a three-seat offline review council for
pre-screening and quality control. Kimi K3 audits source support, Claude Fable
tries to disprove identity, and GPT-6 Astra checks wording and evidence limits.
The orchestrator is deterministic and does not vote. It sends one project per
request, requires exact evidence-packet paths for material claims, keeps each
model's first vote, and runs a separate dissent round only for unresolved
cases. A blocking evidence finding prevents confirmation. Council votes remain
separate from the two human decisions and cannot open the publication gate.
The public Worker has no model dependency.

The completed 120-case council run produced 80 confirmed pre-screening
outcomes and 40 unclear outcomes after a dissent round. Ninety-one cases were
unanimous, and final seat agreement was 75.83 percent. Eighteen invalid attempts
were rejected before a valid replacement was accepted. All 480 saved verdicts
cite one unchanged case packet per round, and every one of the 498 raw attempt
files passes its stored SHA-256 check. This disagreement rate reinforces the
need for independent human review before any link is published.

The private evidence index now covers nine archived FY2027 documents, 5,999
pages and 9,838 searchable passages. Every answerable case in the expanded
40-question evaluation retrieves an expected document, and every citation
passes its file and passage hash check. Six ordinary unsupported questions
still retrieve related passages, but the support gate correctly refuses them
because budget documents are not proof of payment, delivery, audit findings,
ownership, images, or coordinates. Recall, answer support, refusal accuracy,
and citation integrity each measure 100 percent. This permits private testing
only. No public question-answering endpoint exists. Retrieval remains available
only to the private council and research editor as a way to find passages for
review.

## Operational status

The production site and repository tests passed on 17 November 2026. The
project-image workflow published 35,890 checked contracts, including 10,706
exact source-count matches and 4,167 records whose official source reported no
images. Another 21,017 records remain held because the source counts conflict.

The PCAB regular-license table fell from 18,657 to 18,604 rows and crossed its
reviewed floor. A row-level comparison of the archived official responses found
81 removed licenses whose stated validity dates had passed, 28 additions, no
removed active license and no changed retained row. The reviewed floor is now
18,576. The 12 valid licenses already missing from the grid still pass their
exact official detail-page checks and remain explicit source inconsistencies.

Two external sources remain limited. The Senate Budget Transparency Portal
still returns an interactive access challenge to the direct monitor. The
bounded secondary reader passed on 16 November 2026, including its official
lowercase page alias fallback, and six active catalogue records reconciled.
The facility source monitor still reports its source unavailable and keeps that
release held.

The official PSA page lists a 2023 city and municipal poverty workbook covering
1,611 places. The source currently presents an interactive access challenge to
the automatic downloader. A bounded monitor now retries every six hours,
publishes the download status, and keeps all poverty values out of the public
database until the complete workbook, PSGC identities, uncertainty measures,
and published classification totals pass together. CBMS remains excluded
because no reusable national aggregate table with the required geographic
coverage has been acquired.

The weekly audit now checks whether the service attached to an active timer is
currently running before treating a temporarily missing next activation as a
schedule failure. A genuinely inactive timer or a stopped service without a
future activation still fails the audit.

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

1. Keep the automatic PSA poverty check running and publish the 2023 city and
   municipal estimates only after the official workbook passes source, schema,
   PSGC, uncertainty, row-count, and classification-total checks. Keep CBMS
   indicators out until PSA or an LGU publishes reusable aggregate tables with
   clear geographic coverage and no household identifiers.
2. Continue the bounded project-image cycles. Do not increase public coverage
   by weakening source-count, file-integrity or immutable-media checks.
3. Complete two independent human decisions for at least 100 cases in the
   balanced 120-case project-link review batch. Unclear and conflicting cases
   stay out of the public reviewed-project list.
4. Publish only confirmed project links after the review, accuracy, agreement
   and source-total checks all pass. Then add those links to place and district
   summaries without changing unreviewed source records.
5. Refresh the FY2027 publication catalogue and extend the comparison ledger
   when stable Senate, bicameral and final GAA artifacts can be acquired and
   reconciled.
6. Continue the bounded official-source retry runner and acquire award notices,
   signed contracts, completion certificates, inspection and acceptance
   records, payment records and COA findings only when reproducible official
   artifacts can be retained and their identifier limitations modeled.
7. Obtain a licensed, reusable NAMRIA administrative-boundary artifact before
   adding point-in-polygon coordinate validation. Until then, keep exact source
   coordinate checks visibly separate from geographic verification. The
   official Geoportal catalogue labels the available regional, provincial and
   municipal layers approximate and not downloadable, and its WFS endpoint
   currently requires authorization. No unofficial polygon substitute is
   published.
8. Review high-volume name-only contractor identities and quarantine ambiguous
   mergers instead of collapsing similar business names.
9. Add alerts for source drift and publication mismatch without granting the
   monitor deployment or database mutation credentials.
10. Reconcile district and representative changes against a newly archived
   roster snapshot before updating public names, keeping prior snapshot hashes.
11. Expand the completed answer-support evaluation beyond the current 40
   questions, have the answer set reviewed independently, and test exact claim
   citations. Keep public evidence question answering disabled until a separate
   release decision approves the answer-quality and safety contract.
12. Keep the required repository-wide strict type check at zero errors. New
    ingestion, review and publication modules must pass without broad ignores
    before they can merge.

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

Last updated: 2026-11-17.
