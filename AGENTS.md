# Busisi engineering contract

## Scope

This repository contains only the Busisi Philippine budget watchdog. Keep the
public system deterministic, evidence-first and independent of model APIs.

## Data rules

- Preserve original source bytes and SHA-256 provenance.
- Represent money as integer centavos. Never use floating-point arithmetic.
- Validate source boundaries, schemas, fiscal years and control totals.
- Quarantine ambiguous or conflicting identity links.
- Describe review signals as leads for verification, not findings of wrongdoing.
- Never expose the canonical acquisition database to a public request.

## Implementation rules

- Write a failing test before adding behavior.
- Keep functions focused and handle boundary errors explicitly.
- Sanitize generated HTML and use parameterized database queries.
- Do not add secrets, model credentials or model API dependencies.
- Run Python, Worker and production contract tests before release.
- Use commit messages in the form `<type>: <description>`.

## Public language

- Write for a Filipino reader who has no budget, audit, procurement, or data
  background. Put the direct answer before the technical detail.
- Use the headings `What we know`, `What needs checking`, `What this does not
  prove`, `What to check next`, and `Where this information came from` when they
  fit the page.
- Explain an official term the first time it appears. Keep record IDs, source
  check codes, and exact technical states in details or downloads when ordinary
  readers do not need them to understand the answer.
- Do not expose internal workflow words such as provenance, acquisition,
  quarantine, reconciliation, gate, artifact, fingerprint, lifecycle, or
  dossier as public labels. Use the replacements in
  `docs/public-language-standard.md`.
- Test visible copy, page descriptions, empty states, and error states. Run the
  public-language tests before considering a page complete.
