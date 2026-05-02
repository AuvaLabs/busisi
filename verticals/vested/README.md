# Vested vertical

Personal-finance-for-tech-workers platform — second vertical to ship
(per BUILD-DIRECTIVE Phase 5).

Per-vertical files (populated in Phase 5):

- `config.yaml`  — taxonomy (equity-compensation, taxes, retirement-planning, brokerage-investing, ...), entity types (brokerage, bank, credit-card, tax-software, insurance-provider, employer), dedup guards (ticker symbols, IRS publication numbers)
- `sources.yaml` — 30-50 feeds: IRS publications (1.0), SEC filings, FRB economic data, Treasury, brokerage announcements, tax software releases, Levels.fyi, WSJ Personal Finance, Mr. Money Mustache, ChooseFI, White Coat Investor, ...
- `prompts/`     — same role set as Modelwatch but Vested-specific. CRITICAL: every tax/legal prompt must include "this is general information not professional advice" framing.
- `overrides/`   — per-vertical templates and content (more conservative tone than Modelwatch; YMYL trust bar)

Design accent: deep teal `#2D5F5D` (light), `#5A8E8C` (dark) — see `docs/design-derivation.md`.
