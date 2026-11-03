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
