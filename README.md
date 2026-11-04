# Busisi

*Follow public money. Check the evidence.*

Busisi is a nonpartisan public-interest data platform that helps Filipinos
follow public money from proposal to project delivery. It publishes official
source records, deterministic review signals,
an FY2027 NEP-to-House project ledger, a national appropriation-head ledger,
an FY2027 source-separated budget publication trail, a reconciled FY2026
allotment-release ledger, and a small reviewed dossier set
without using a language model. A separate COA evidence layer records which official
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

The project-integrity desk publishes deterministic DPWH source contradictions,
coordinate review signals and coverage gaps. Its contractor view separately
ranks archived activity by project count and total project budget. Neither view
uses a model or produces a corruption score.

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
PYTHONPATH=. python3 ops/harness/budget_watchdog_coa.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_contract_evidence.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_acquisition_release.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_acquisition_universe.py
PYTHONPATH=. python3 ops/harness/budget_watchdog_acquisition_retry.py --limit 10
cd cloudflare/busisi
npm ci
npm run check
npm run verify:live
```

Generated data and local publication bundles are written under
`data/budget_watchdog/` and are not committed.

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

The project-image evidence queue runs every six hours. Each cycle starts with a
25-contract canary, continues in 100-contract chunks and processes at most
1,000 contracts with four workers paced to two requests per second per source
host. Eight healthy cycles raise the limit to 2,000. Repeated rate limits or a
retryable failure ratio above 10 percent stop the cycle and reduce its next
workload.
Every successful record still requires archived source bytes, detail-to-list
count reconciliation, JPEG inspection and a gated D1 release. The bulk project
feed is used only for discovery because it does not provide the exact image-list
count needed for this evidence contract.

The local acquisition retry timer runs one bounded batch daily. It accepts only
registered official DPWH HTTPS origins, archives successful source bytes, uses
exponential backoff for retryable HTTP failures, and blocks a task after the
configured attempt limit for review.

## License

Proprietary.
