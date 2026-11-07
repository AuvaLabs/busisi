# Roadmap audit, 2026-11-07

This audit records what Busisi could verify, what remains unavailable and what
must not be published yet. It does not turn a blocked source into evidence.

## Senate catalogue monitor

The official FY2027 Senate catalogue currently returns a Cloudflare challenge
to the bounded monitor. The secondary text renderer returns the same challenge.
The monitor still exits with an error so a missed source refresh cannot look
healthy. It now saves both final responses, their HTTP status, size and
SHA-256 digest in the run artifact before failing.

The 2026-11-07 local reproduction recorded:

- official portal: HTTP 403, 6,046 bytes,
  `0c71599933eb47886b1db26e1a13252caae0f96aaf5d45ac004d360ebfea1b35`;
- secondary renderer: HTTP 200 containing the challenge, 6,010 bytes,
  `e2090f8f0f1a36b6025be1490fa2c779c52de8c442c4991d832ccb4ea8b731dc`.

The reviewed five-record FY2027 publication catalogue remains unchanged. The
monitor cannot confirm a fresh observation until one of the bounded paths
returns the real catalogue.

## Private evidence retrieval

The index contains nine archived FY2027 documents, 5,999 extracted pages and
9,838 searchable passages. The expanded 40-case evaluation found:

- 28 of 28 answerable questions retrieved an expected document;
- every returned passage matched its stored file and passage hashes;
- six synthetic no-match questions returned no result;
- six ordinary unsupported questions retrieved related passages, but every
  passage was correctly recognized as the wrong kind of evidence; and
- answer support and unsupported-question refusal both measured 100 percent.

The support gate permits private testing of retrieval packets. It does not
approve generated answers or public release, and no public question-answering
endpoint exists.

## Private council completion

The three-seat council completed all 120 prepared project-link cases. Every
case has three valid first-round decisions. Forty unclear cases also have three
valid dissent-round decisions.

- final outcomes: 80 confirmed pre-screens and 40 unclear;
- final unanimous cases: 91;
- final seat agreement: 75.83 percent;
- saved verdicts: 480;
- saved attempts: 498;
- invalid attempts rejected before replacement: 18; and
- human decisions: zero.

The audit verified every raw attempt file against its stored SHA-256 digest,
one unchanged packet hash per case and round, three distinct seats per round,
all 120 automated source prechecks and SQLite integrity. The council remains
private because its votes are not independent human review and its agreement
does not meet the 95 percent publication standard.

## Official geographic boundaries

Geoportal Philippines identifies itself as the official Philippine GIS
platform. Its session-backed layer catalogue listed three NAMRIA layers that
are relevant to Busisi:

| Layer | Geoportal title | Download state |
|---|---|---|
| `regionalboundary_20210504` | Regional Boundary (APPROXIMATE) | Not downloadable |
| `provincial_boundary_wgs84` | Provincial Boundary (APPROXIMATE) | Not downloadable |
| `municipalbndry_20210504` | Municipal Boundary (APPROXIMATE) | Not downloadable |

The responses are retained under the private ignored data directory. Their
SHA-256 digests are:

- layer catalogue:
  `4ea8045a7fbd2916018f09f31d9dd7a43ef29c90a8a98d207392e38732a87558`;
- layers by agency:
  `1b1e21e8fd292a5ec3a00c573a780261bce33dab942e29d0bfcdc30e4115e0f1`;
- WMS link catalogue:
  `8f6858e1e66a14a72fb5189e7e5db97049d95e0c7dc4038c69e5c5ab38f4c1d2`;
- WFS response:
  `c5aa9d50862037c6ad56b830145761d8fc5bd6796ea369cf4e64112013d43159`.

The WFS feature-service request returned HTTP 401, and the website's download
flow requires a person to provide contact information and accept the data
owner's terms. Busisi therefore has no reusable polygon artifact and still
does not perform point-in-polygon validation. An unofficial substitute would
weaken the evidence standard and was not used.

## Official contract evidence

The bounded acquisition retry runner completed successfully but claimed zero
items because no queued item was due at the audit time. It did not invent a
new result or change any lifecycle state. The next scheduled retry remains the
correct path for blocked or not-located official documents.

## Maintenance verification

The seven open dependency updates were reproduced together in an isolated
Python 3.12 environment. The updated runtime and development requirements
installed successfully. The full Python suite passed with 635 tests and 90.53
percent combined coverage. The Worker suite passed with 115 tests, 98.94
percent line coverage and 90.08 percent branch coverage. Strict type checking
passes all 98 engine modules, and GitHub now requires both Ruff and mypy in the
main test job. The Cloudflare dry deployment also passed.

The cumulative project-image bundle now reuses verified content-addressed
archive bytes with same-filesystem hard links and falls back to a byte copy
when links are unavailable. This removes the repeated 14 GB media copy from
normal coverage cycles without changing the file digest checks or publication
gate.

The read-only production audit passed with no issues. It verified 68,608
budget records, 56,887 delivery records, 20,431 stage changes, 16,814
integrity signals, 4,297 contractor identities and 96 allotment-release
records. The gated image-coverage release now contains 9,649 completed
contract checks: 3,184 exact image sets, 817 records reporting no images and
5,648 count conflicts. The remaining private queue has 43,427 pending, 3,812
blocked and two retry records. All four unattended pipeline timers are active,
the private queue passes SQLite integrity checking and no lease is expired.

## Remaining publication decisions

- Model council votes are private quality checks and cannot be described as
  human review.
- New project links still require two independent human decisions for at least
  100 cases and the existing accuracy, agreement and source-total thresholds.
- Public evidence question answering remains disabled until a separately
  reviewed answer set passes and a release decision approves the public safety
  and answer-quality contract.
- Geographic validation remains disabled until a licensed, versioned official
  polygon file can be retained and reproduced.
