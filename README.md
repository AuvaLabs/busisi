# Busisi

*Follow the evidence behind public projects.*

Busisi is an independent, nonpartisan evidence desk that helps Filipinos
follow the records behind Philippine public projects. It connects budget,
procurement, contractor, delivery, audit and payment evidence while keeping
unsupported stages visible as gaps. Its public ecosystem is organized around
projects, contractors, recorded places, questions that need checking, sources
and source monitoring. It publishes official source records, deterministic
review signals,
an FY2027 NEP-to-House project ledger, a national appropriation-head ledger,
an FY2027 source-separated budget publication trail, a reconciled FY2026
allotment-release ledger, complete delivery-record dossiers and a smaller set
of reviewed cross-source project links. A separate COA evidence layer records which official
audit catalogues were checked, whether source bytes were acquired, and whether a
project-level observation was actually matched. Contract outcome cross-checks
compare exact procurement records with the DPWH delivery snapshot while keeping
award, awardee, inspection and payment evidence states explicit. A complete
version-pinned BetterGov PhilGEPS mirror snapshot is archived with its original
bytes and SHA-256. It remains secondary evidence and is never labelled an
official award notice.
For three reviewed contracts, a separate acquisition ledger tracks nine target
documents from procurement planning through payment. Each target is classified
as archived official evidence, an indexed but unarchived source, a blocked
acquisition, secondary mirror evidence or a document not located. A date
reported in a monitoring row never substitutes for the underlying document.

The acquisition universe covers all 56,887 FY2024 to FY2026 DPWH delivery
contracts. The deterministic scan found usable exact secondary rows for 47,071
contracts, no exact mirror row for 9,655, and conflicting exact identifiers for
161. It retained 62,129 exact rows, quarantined 83 conflicting source rows, and
created 511,983 lifecycle tasks. The canonical queue stays local. Read-only
contract states, exact secondary rows, quarantined conflicts, reconciled
counts, source identity and limitations are published to D1. Every contract
has a human-readable drill-down. Review decisions and the mutable queue remain
local.

The public review desk ranks stage changes, groups monetary movement by region,
office, program or dataset, identifies conservative cross-year project-family
candidates, and exports source-linked CSV evidence.

The public evidence question catalogue states what the current publication can
answer, what remains only partially answerable, and what cannot yet be
established. Its counts and dates are derived from the same D1 release controls,
and every supported question links to a reader-facing evidence desk with an
explicit limitation. The catalogue is also available at `/api/v1/questions`.

The research library at `/research/` publishes bounded investigations from the
same evidence system. Each article has an authenticated, versioned data package
with claim states, calculations, sources, limitations, chart data, and project
examples. Discovery services may help locate documents privately, but public
claims identify and archive the underlying publisher's evidence. Published
work currently examines multipurpose-building records at
`/research/multipurpose-buildings/` and FY2027 NEP-to-House project-list
changes at `/research/fy2027-nep-house-changes/`. A separate concentration
investigation at `/research/fy2027-change-concentration/` groups the same
authenticated comparison by recorded program, region, office and dataset
labels without inferring political responsibility or wrongdoing.

The multipurpose-building investigation now reconciles ₱88.79 billion in the
active pipeline and ₱129.78 billion across all classified FY2024 to FY2026
records. It also publishes official classroom funding-scale comparisons and
explicit evidence categories for need, location, design, cost, and delivery. Missing
planning evidence is reported as not assessable, never as proof that a project
is unnecessary or improper.

Its public-value evidence layer opens a bounded queue of 43 project records:
31 exact-coordinate history review leads and 12 of the largest active recorded
budgets. The project-level checklist separates source-reported fields from
missing identity, need, site, design, cost, delivery, and actual-use evidence.
Selection is not a risk score or finding of wrongdoing.

The targeted acquisition layer expands those 43 records into 946 evidence
checks. The current reconciliation keeps 28 exact secondary award rows, two
archived DPWH source-media records, and 34 indexed official-procurement records
as separate lead types. Nineteen official DPWH document URLs cover 17 queued
contracts, but no official source file is called verified because the host
returned HTTP 403 and no source bytes were archived. Three contract identity
conflicts are quarantined. A lead never passes an evidence gate by itself.

Its immutable downstream editorial package is published under
`/data/research/multipurpose-buildings/v6/`. The consumption index provides the
finished story, checked claims, chart data, project examples, direct source
links, limitations, API route, and SHA-256 manifest without requiring changes
in a downstream production repository.

The public correction and release register is `/research/releases/`. It keeps
every immutable version visible and distinguishes a correction from a data
update or an editorial expansion. Research ideas, evidence gaps and production
readiness remain in the ignored private queue under
`data/budget_watchdog/research-editor/`; only completed editorial packages are
available for downstream consumption.

The public update feed at `/feeds/updates.xml` and `/api/v1/alerts` reports
checked source status, gated coverage releases, newly checked contract evidence
and deterministic review questions. Every item includes an evidence boundary.
The feed is bounded to 30 items and never exposes the private acquisition queue.

The public-services inventory separately classifies acquired budget-stage rows
and DPWH delivery contracts whose titles explicitly name schools, hospitals or
health facilities. It labels work wording and deterministic review flags, but
does not count the rows as unique facilities or claim construction, completion,
payment, quality or public benefit. The reader desk is `/public-services/`; its
machine-readable records and controls are `/api/v1/public-services` and
`/api/v1/public-services-summary`.

A scoped facility-identity pipeline can reconcile school-related records with
the Department of Education's indicative list of 1,095 possible PPP sites in
eight announced regions. It requires the original workbook, its SHA-256 digest,
the 1,095-row control total, valid school IDs and coordinates, and an exact
school-name-and-place match. Repeated names, missing places and conflicts remain
quarantined. The source currently blocks unattended acquisition, so no identity
from this pilot is published until those controls pass. The pipeline does not
turn a listed school or linked record into a building count.

The DepEd source monitor runs every six hours. HTTP 403 is published as a known
blocked state, while disappearance, transport failure, schema drift and control
total failure require operational review. When the official workbook becomes
available, the pipeline creates a complete candidate packet but withholds every
inferred link until a manifest bound to that exact source and candidate set has
at least 100 reviewed cases, at least 95 percent precision, at least 95 percent
reviewer agreement and zero critical reconciliation failures.

The project-integrity desk publishes deterministic DPWH source contradictions,
coordinate review signals and coverage gaps. Its contractor view separately
ranks archived activity by project count and total project budget. Neither view
produces a corruption score.

The contractor-accountability desk links official GPPB restriction records only
when the normalized DPWH name and current PCAB name agree on one identity. It
links low CPES ratings by exact PCAB ID. Exact rows from the archived secondary
award mirror can create a dated review question, but are never presented as an
official award document or proof of corruption, political connection or an
improper award. Name-only and unmatched records remain quarantined.

Where the listed DPWH office has an exact roster mapping, records also show the
roster-snapshot congressional district and representative. Shared offices retain every
possible district, and unmatched offices remain unassigned. This context does
not imply project sponsorship, control or responsibility.

Production: [busisi.org](https://busisi.org)

## Mission and editorial independence

Busisi exists to help Filipino citizens understand how public money is
proposed, changed, released, procured and implemented. It is nonpartisan and
has no affiliation with any politician, political party, candidate or
government faction. It does not endorse or oppose candidates, parties or
public officials.

Every agency, district, contractor and public official is evaluated under the
same published evidence rules. Busisi does not infer motive from a budget
amount, project location, contractor identity or political name. Records,
derived comparisons, review signals and verified findings remain visibly
separate. Coverage limitations and corrections are published so readers can
inspect where the data ends and challenge an error using source evidence.

## Project and data attribution

Busisi is built and maintained by [Auva Labs](https://auvalabs.com/).
Questions, corrections and collaboration enquiries can be sent to
[dev@auvalabs.com](mailto:dev@auvalabs.com).

Auva Labs is responsible for Busisi's software, data pipeline, methodology,
presentation and publication decisions. Data-source organizations do not
control Busisi classifications or conclusions.

Busisi uses public datasets and API endpoints maintained by
[BetterGov.ph](https://bettergov.ph/) and the
[bettergovph GitHub organization](https://github.com/bettergovph), including
GAA, DPWH delivery and version-pinned PhilGEPS mirror inputs. Busisi preserves
the acquired source bytes and fingerprints, performs its own deterministic
validation and reconciliation, and keeps BetterGov-derived records distinct
from original agency publications. BetterGov does not operate Busisi and is not
responsible for Busisi review signals, interpretations or publication choices.

## Accuracy contract

The publication pipeline follows this order:

1. Acquire and hash official source artifacts.
2. Archive original bytes and record provenance.
3. Validate schemas and fiscal years.
4. Normalize monetary values as integer centavos.
5. Reconcile control totals.
6. Match identities using deterministic evidence.
7. Classify confidence and calculate review signals.
8. Quarantine ambiguous links.
9. Publish read-only records with sources and limitations.

A signal identifies a record for further review. It is not a finding of
wrongdoing. Inferred links do not publish automatically until the reviewed
golden set reaches the documented precision gate.

## Repository layout

| Path | Purpose |
|---|---|
| `engine/budget_watchdog/` | Acquisition, archive, validation, normalization, matching, signals and publication builders |
| `engine/tests/budget_watchdog/` | Unit and integration tests |
| `ops/harness/` | Deterministic data, site and publication verification commands |
| `cloudflare/busisi/` | Production Worker, D1 schema, public interface and live verifier |
| `docs/` | Build contract, design system and dated data snapshots |

## Verify locally

```bash
python -m pip install -r requirements-dev.txt
PYTHONPATH=. pytest engine/tests/budget_watchdog -q
PYTHONPATH=. python3 ops/harness/budget_watchdog_golden.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_hgab.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_agencies.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_allotment_releases.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_districts.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_integrity.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_senate.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_senate_monitor.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_source_monitor.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_pcab_transition.py --help
PYTHONPATH=. python3 ops/harness/budget_watchdog_coa.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_contract_evidence.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_acquisition_release.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_acquisition_universe.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_acquisition_retry.py --limit 10
PYTHONPATH=. python3 ops/harness/budget_watchdog_facilities.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_facility_monitor.py --reset-output
PYTHONPATH=. python3 ops/harness/budget_watchdog_accountability.py --source-only --reset-output
PYTHONPATH=. python3 ops/harness/budget_watchdog_accountability.py --reset-output
PYTHONPATH=. python3 ops/harness/budget_watchdog_research.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_scheduled_audit.py --cadence weekly
cd cloudflare/busisi
npm ci
npm run check
npm run verify:live
```

Generated local data and publication bundles are written under
`data/budget_watchdog/` and are not committed. Authenticated public research
packages under `cloudflare/busisi/public/data/research/` are versioned deployment
inputs and are committed with the code that renders them.

## Runtime

The public service is a read-only Cloudflare Worker backed by an isolated D1
publication database. The canonical acquisition database is never bound to a
public request. The publication database contains derived read-only evidence,
never the local review queue or reviewer decisions. Production monitoring is
credential-free and read-only.
The Senate catalogue monitor runs every six hours, preserves its bounded source
responses as workflow evidence, and fails closed when records change or source
acquisition becomes unreliable. It never updates the reviewed baseline
automatically.

The source drift monitor independently checks the BetterGov GAA, DPWH and
PhilGEPS revisions, the DBM allotment-release catalogue, the district roster and
the PCAB regular-license table every six hours. Changed source observations are
archived and reported, but never replace a reviewed publication automatically.
The public `/coverage/` page exposes the latest result and its known discovery
limits. The local operational audit also verifies queue integrity, lease age,
publication markers, timer health and the complete live production contract.
COA catalogue discovery remains an explicit manual coverage limit because the
official catalogue blocks unattended acquisition.

PCAB record-count reductions require a row-level transition review between two
archived, hash-verified official snapshots. The review permits removal only for
licenses whose stated validity date has passed, rejects changed retained rows
or removed active rows, and records the reviewed hashes and control totals
before the floor can be changed.

The project-image evidence queue runs every six hours. Each cycle starts with a
25-contract canary, continues in 100-contract chunks and processes at most
1,000 contracts with four workers paced to two requests per second per source
host. Eight healthy cycles raise the limit to 2,000. Repeated rate limits or a
retryable failure ratio above 10 percent stop the cycle and reduce its next
workload.
Pending work is ordered by disclosed priority factors: an existing reviewed
dossier, source image availability, project value, a stated joint venture,
repeated contractor activity, deterministic evidence questions and qualifying
COA evidence. Lower priority scores run first. Priority refreshes preserve all
existing task states and require the same source hash, seed count, identifiers,
years and image hints.
Every successful record still requires archived source bytes, detail-to-list
count reconciliation, JPEG inspection and a gated D1 release. The bulk project
feed is used only for discovery because it does not provide the exact image-list
count needed for this evidence contract.

The local acquisition retry timer runs one bounded batch daily. It accepts only
registered official DPWH HTTPS origins, archives successful source bytes, uses
exponential backoff for retryable HTTP failures, and blocks a task after the
configured attempt limit for review.

The six-hour operational audit satisfies the daily freshness requirement. A
weekly timer retains a coverage and source audit report. A monthly timer runs
the operational audit, the complete Python test suite, the Worker tests, every
data-bundle control and a Cloudflare deployment dry run. Any failed or timed-out
check makes the scheduled report fail closed.

## License

Busisi source code and project documentation are licensed under the
[Apache License 2.0](LICENSE), unless a file states otherwise. The license does
not relicense government records, third-party datasets, source media, fonts, or
trademarks. See [NOTICE](NOTICE), [DATA_AND_MEDIA.md](DATA_AND_MEDIA.md), and
[third-party notices](cloudflare/busisi/THIRD_PARTY_NOTICES.md).

Public corrections and software contributions are welcome under
[CONTRIBUTING.md](CONTRIBUTING.md). Report vulnerabilities privately using
[SECURITY.md](SECURITY.md). Questions can be sent to
[dev@auvalabs.com](mailto:dev@auvalabs.com).
