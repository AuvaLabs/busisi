# Contributing to Busisi

Busisi welcomes corrections and improvements that make Philippine public
budget evidence easier to inspect and verify.

## Contribution boundaries

Every contribution must preserve these rules:

- Use traceable public evidence and identify the original publisher.
- Keep source records, derived comparisons, review signals, and verified
  findings separate.
- Apply the same deterministic rule to every agency, district, contractor,
  project, and public official.
- Do not infer corruption, political motive, sponsorship, responsibility, or
  benefit from an amount or association alone.
- Keep unavailable, conflicting, and quarantined evidence visible.
- Do not add credentials, private review material, generated acquisition data,
  or personal information.
- Do not claim that a source provider operates, sponsors, or endorses Busisi.

## Before opening a pull request

1. Open or reference an issue that describes the correction or behavior.
2. Add or update a failing test before changing behavior.
3. Preserve source URLs, acquisition dates, hashes, units, and evidence
   boundaries where applicable.
4. Run the Python and Worker checks documented in `README.md`.
5. Keep generated files under `data/` out of the commit.
6. Confirm that the change is compatible with the repository license and the
   separate data and media terms.

Pull requests should be focused, explain the public value of the change, name
the evidence used, and disclose known coverage limitations. Submission does
not guarantee publication. Auva Labs retains responsibility for Busisi
methodology, presentation, and publication decisions.

## Corrections

For a public-data correction, include the exact Busisi URL or record ID, the
current value, the proposed correction, and a source that supports it. A news
article or social-media post may identify a question but is not a substitute
for the underlying record.

For private security reports, follow `SECURITY.md` instead of opening an issue.
