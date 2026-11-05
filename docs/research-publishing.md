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

## Build and release

The public packages are regenerated and verified with:

```bash
cd cloudflare/busisi
npm run build:research
```

The harness verifies archived source SHA-256 identities, rebuilds every payload, checks control totals, and writes authenticated manifests. A changed source or changed control total fails the build. Public packages can be checked without private acquisition data using:

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
