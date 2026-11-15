# DPWH project-type snapshot

This release adds a public project-type explorer for the saved BetterGov DPWH
delivery dataset. The source artifact is unchanged from the verified delivery
release. Its SHA-256 is
`5b411cf3f112fabd1913c70681791e5e2b78b43a8393f489f48bd882f154e123`,
and the upstream bulk file reports 22 January 2026 as its last modification
date.

## Release controls

| Control | Result |
| --- | ---: |
| Saved project records | 56,887 |
| Records with at least one supported label | 56,372 |
| Records left without a guessed label | 515 |
| Total overlapping labels | 205,101 |
| Classification rule version | 1 |
| Integrity bundle SHA-256 | `82627df4e532d6472615b9c22acbb6a2ccf2923dcc0254a469becc3e9735cf9f` |

The total label count is larger than the record count because one project can
state several physical types, purposes, or kinds of work. A bridge with an
access road and drainage, for example, remains visible in all supported groups.

## Physical project types

| Label | Records |
| --- | ---: |
| Road | 25,490 |
| Public building or facility | 23,583 |
| Multipurpose building | 12,609 |
| Flood control or drainage | 11,695 |
| Bridge | 7,337 |
| School or classroom | 4,441 |
| Water system | 1,123 |
| Hospital or health facility | 709 |
| Port or harbor | 411 |
| Evacuation center | 407 |

## What the labels mean

Labels use only phrases in the project title or its source category. Physical
type, public purpose, type of work, and named funding program are stored
separately. Every label records the rule version and whether its support came
from the title, category, or both.

These labels do not establish need, physical existence, completion, payment,
quality, public benefit, wrongdoing, or whether several contracts refer to one
physical facility. Those questions require other records. The explorer does
not merge contracts or use a model to fill missing evidence.
