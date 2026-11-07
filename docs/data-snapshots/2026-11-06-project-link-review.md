# Project-link review batch, 2026-11-06

Busisi prepared a private, balanced batch for expanding reviewed links between
approved-budget records and DPWH project records. This file describes the
selection. It does not claim that any newly selected link has passed review.

## Source pool

- 20,877 high-confidence, one-to-one candidates from FY2024 and FY2025
- 20,877 matching saved DPWH detail records
- both saved-source check codes present for every selected case

## Selected batch

- 120 cases
- 60 FY2024 and 60 FY2025 cases
- 20 cases in each broad project type: roads, buildings, flood control,
  bridges, water systems and other public works
- 30 cases in each project value band
- all 17 recorded regions represented with seven or eight cases each
- 22 joint records
- 36 cases with at least one existing question to check
- 119 distinct recorded contractors
- 120 of 120 cases passed the automated source reconciliation for titles,
  years, amounts, places, funding source, allowed source links and both
  saved-file check codes

Selection SHA-256:
`569934aa207c5d4d9430d835c0f708bc6a1eb1d58aef6a7fcfa1f7b8252b1bfa`

## Publication boundary

The workspace starts with zero reviewed cases. Each case requires two
independent decisions supported by a source link, saved-file check code, note
and review time. Busisi publishes new reviewed links only after all of these
conditions pass:

- at least 100 cases have two decisions;
- at least 95 percent of proposed links are confirmed;
- the two reviewers agree in at least 95 percent of cases; and
- no critical source-total check remains unresolved.

Unclear, rejected or conflicting cases remain outside the public
reviewed-project list.

## Offline council calibration

Busisi also ran a private model-assisted quality-control pilot on the first 20
cases. This is a pre-screening layer, not human review and not a publication
decision.

- source-support seat: Kimi K3
- identity-skeptic seat: Claude Fable
- public-quality seat: GPT-6 Astra
- one project per request, scheduled through a bounded three-worker queue
- 60 valid first-round votes
- one invalid first-round response rejected for an unsupported generalization,
  then replaced by one valid retry
- nine valid dissent-round votes across three unclear cases
- 17 confirmed cases and three unclear cases after the dissent round
- zero rejected or incomplete cases
- 19 of 20 cases ended with unanimous final votes; the remaining case stayed
  unclear with a blocking finding
- zero human decisions recorded

Every identity basis, finding and gap must cite an exact JSON Pointer path in
the evidence packet. The runner rejects nonexistent paths and wording that
uses unsupported claims about what is normal, common, usual or typical.
BetterGov records are labelled as civic mirrors rather than official
government pages. A blocking evidence finding prevents confirmation.

The council is fail-closed and remains private. Its 69 valid votes do not count
as the two independent human decisions required by the publication gate. The
public Worker has no model or model API dependency.

## Full-batch council run, 2026-11-07

The same three-seat process was then completed across all 120 cases. This was
still private pre-screening and did not create a human review decision.

- 360 valid first-round decisions, three per case
- 40 unclear first-round cases sent to a three-seat dissent round
- 120 valid dissent-round decisions
- 80 confirmed pre-screening outcomes after the dissent round
- 40 unclear outcomes after the dissent round
- zero rejected or incomplete cases
- 91 unanimous final outcomes
- 75.83 percent final seat agreement
- 498 saved attempts, including 18 invalid attempts rejected by schema or
  evidence-path validation before a valid replacement was accepted
- 4,076,887 recorded input tokens, including 2,579,646 cached input tokens
- 988,261 recorded output tokens and 276,508 recorded reasoning tokens
- zero human decisions recorded

An integrity audit confirmed one unchanged evidence-packet hash per case and
round, three distinct seats per completed round, all 120 source prechecks, all
480 verdicts and the stored SHA-256 digest of every raw attempt file. The
private SQLite database passed its integrity check.

The 75.83 percent model-seat agreement is below the human publication standard
and is not converted into an accuracy claim. It demonstrates where the source
records need closer review. The public release remains closed until at least
100 cases receive two independent human decisions and all existing thresholds
pass.
