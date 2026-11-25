# Research publishing

Busisi research releases answer a bounded public question with reproducible calculations, evidence states, and explicit limitations. The public article and downstream content package must use the same immutable release.

## Public release contents

Each release is stored under `cloudflare/busisi/public/data/research/<slug>/v<version>/` and contains:

- `manifest.json` with the source identity, release state, file digests, and package digest
- `claims.json` with stable claim identifiers and evidence states
- `findings.json` with reader-facing results linked to claim identifiers
- `investigations.json` with the question, result, state, and calculation rule
- `chart-data.json` with exact chart and table values
- `project-examples.json` with bounded examples and reader URLs
- `sources.json` with publisher, access route, scope, and artifact identity
- `limitations.json` with release-wide interpretation boundaries
- `story.json` with the finished, ordered editorial story and evidence references
- `editorial-package.json` with absolute links to the story, data, direct sources, API, and integrity manifest

Drafts, rejected leads, scripts, and production instructions do not belong in the public repository. Private editor drafts live under the ignored `data/budget_watchdog/research-editor/drafts/` path. A downstream publisher consumes the ready package without requiring changes to its own repository or research workflow.

The story marks each section as narration eligible or as an investigation lead. Only `verified` and `source_reported` claims may appear in narration-eligible sections. A review candidate must remain a non-narratable investigation lead with an explicit limitation.

## Evidence states

- `verified` means the stated calculation is reproducible from the registered source artifact.
- `source_reported` means the value or status is reproduced from the source and is not independently confirmed.
- `review_candidate` means a deterministic pattern needs additional evidence.
- `partial` means the acquired evidence answers only part of the question.
- `evidence_gap` means the required evidence is not available in the release.

## Source quality

Exa and Perplexity may be used privately to discover documents and test a
research question. They are discovery services, not evidence publishers. A
public claim must identify the document that supports it, its publisher, a
direct HTTPS URL, retrieval date, source kind, and the SHA-256 identity of the
archived bytes.

For `verified` and `source_reported` claims, at least one linked source must be
an official record, official dataset, or curated extract of official records.
Academic research, established reporting, and civil-society research may add
context or corroboration. They do not replace the primary record for a budget,
contract, release, payment, or implementation-status claim.

The package writer fails closed when a claim names an unknown source, a source
lacks its archive identity, or a discovery-service URL is presented as
evidence. Source disagreements remain visible as limitations or unresolved
questions.

## Community needs and country comparisons

A comparison must help a reader answer a practical question. It must not exist
only to produce a ranking. The private queue stores a bounded comparison plan
when a topic compares places, needs, or countries. That plan names the reader
value, peer places, measures, denominators, reference-year rule, and evidence
required before publication.

The first comparison set uses Philippine regions, provinces, and legislative
districts for local need questions. The initial international peer set is
Indonesia, Malaysia, Thailand, and Vietnam for education and service-delivery
questions. Indonesia and South Korea are the initial references for comparing
the public record trail from budget approval to implementation. A story may use
fewer peers when definitions or years do not match. It may not silently replace
a missing peer or measure.

Every released comparison must:

- use archived official Philippine records and official or multilateral peer data;
- show the source publisher, reference year, definition, unit, and denominator;
- compare like with like, using the same year and definition for every displayed value;
- normalize large totals using a relevant denominator such as residents, households,
  enrolled learners, exposed people, land area, road length, gross domestic product,
  or total government spending;
- keep appropriation, release, award, payment, completion, and audit values separate;
- show missing and non-comparable values instead of estimating them without evidence;
- display the underlying measures separately and never hide them inside a combined
  need, quality, or risk score; and
- state what the comparison does not prove, including that spending does not by
  itself prove need, quality, protection, completion, or public benefit.

If the same-year source files, shared definitions, geographic identifiers, or
required denominators are missing, the topic remains blocked in the private
queue. A blocked topic is not available to downstream publishers. This rule
also applies when a compelling national total exists but the local evidence
needed to answer the public question does not.

New public research stories use the versioned `question-led-v1` format. The
headline is a question a reader may actually ask. `The short answer` comes
first and must stand on its own. One to four body sections follow, with headings
written from the actual findings rather than reused category labels. A country,
place, or year comparison appears only when its source years and definitions
match. The story ends with a specific account of what the records do not show.

The article package also identifies each next check by the office that holds
the answer, the record needed, and the question that record could settle. The
method summary states how the question is defined, the reference years, units,
and denominators. The public page keeps that technical material and the source
register in expandable details instead of interrupting the answer.

Do not add a standing `Why it matters` section, reuse a standard paragraph of
caveats, or pad a thin result to match another article. Put a necessary caveat
beside the figure it qualifies. Let the evidence determine the number of body
sections, the chart position, the comparison, and the article length. No
sentence should be reusable unchanged in an unrelated Busisi article.

## Editorial cadence

Busisi targets one complete research article each week. A second publication
may be a short evidence update, correction, new official release, or follow-up,
but only when its authenticated package is already ready. The weekly target is
not a content quota. If the required source files, calculations, or review are
incomplete, the article remains in the private queue and no substitute article
is generated merely to fill the calendar.

Source monitoring and data refreshes continue independently of the article
schedule. A changed source may update a public status or open a research task,
but it does not become an article until the normal publication checks pass.
This produces a normal target of four complete investigations per month, with
up to four shorter updates when the records support them.

The first release under this cadence asks what changed in the FY2027
health-facility project list. It publishes the checked 746-row comparison at
`/research/fy2027-health-facility-changes/` and keeps the source control gap,
row-matching limits and missing later budget stages beside the result.

## Build and release

The published package register and every existing package are verified with:

```bash
cd cloudflare/busisi
npm run build:research
```

Published versions are not regenerated from newer local evidence. A new package
is built once by its release-specific harness, then remains unchanged. The
FY2027 health-facility release is built and checked with:

```bash
cd cloudflare/busisi
npm run publish:research:health-facilities
```

The release harness verifies saved source SHA-256 identities, rebuilds the new
payload, checks control totals, and writes its authenticated manifest. A changed
source or changed control total fails the build. Public packages can be checked
without private acquisition data using:

```bash
PYTHONPATH=. python3 ops/harness/budget_watchdog_research_editor.py
```

To publish complete local drafts, place a full release object in the ignored `drafts` directory and run the editor with `--publish-ready`. Invalid drafts are reported as quarantined and nothing from them is copied into the public tree. Existing release directories cannot be overwritten.

The private research queue is initialized once and then validated with:

```bash
PYTHONPATH=. python3 ops/harness/budget_watchdog_research_queue.py --initialize
PYTHONPATH=. python3 ops/harness/budget_watchdog_research_queue.py
```

The queue file and its operational receipt remain under ignored local data. A topic is downstream ready only after it has a published Busisi editorial-package URL. Blocked topics must name the missing evidence. No queue question, source list, working note, or production instruction is copied into the public site.

`release-history.json` is rebuilt from authenticated manifests and the explicit release notes in `ops/harness/fixtures/research_release_notes.json`. Each package must have one note. Later versions must identify the immediately prior package and its SHA-256 digest. Corrections, data updates, and editorial expansions remain separate public labels.

Schema 1.1 releases also fail when their source check is older than the declared maximum age, their story references an unknown claim or source, or a review candidate is marked eligible for factual narration. GitHub verifies every public package weekly. The source monitor separately checks the FY2027 comparison source revision every six hours and reports drift for review. Source changes do not create or publish a new story automatically.

Published packages are never edited in place. A correction or contract expansion creates a new version whose manifest identifies the previous release in `supersedes`. Earlier versions remain available after a newer release becomes current.

Project evidence queues publish selection reasons, gate states, direct dossier links, and missing-evidence boundaries in the immutable package. Entry in a queue is never presented as a risk score, accusation, or finding that a project is unnecessary, duplicated, improperly located, overpriced, or associated with wrongdoing.

The multipurpose-building acquisition harness expands each selected record into
22 deterministic checks across identity, need, location, design, procurement,
delivery, payment, and use. Its mutable SQLite queue and task-level source URLs
remain private. The public package exposes only reconciled coverage counts,
task definitions, source identities, limitations, and per-project gate counts.
Exact rows from a secondary award mirror and archived DPWH source media remain
lead states. Neither state satisfies an official evidence requirement.

## Private document retrieval

The research editor may use the private evidence-retrieval index to locate
passages in archived, hash-verified budget documents. The retrieval command
writes a private packet under `data/budget_watchdog/research-editor/` and marks
every passage `review_candidate`. An editor must check the cited page and
archived source before moving a claim to `verified` or `source_reported`.

Retrieval packets, search scores, optional vectors, and working questions are
not public release files. A missing search result is an evidence gap, not proof
that no budget record exists. See `docs/evidence-retrieval.md` for commands and
the complete boundary.
