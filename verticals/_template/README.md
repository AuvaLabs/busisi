# Vertical template

Skeleton for new Grimoire verticals. Copy this directory, rename, and
populate per-vertical files.

Required files:

- `config.yaml`  — taxonomy (topic labels), entity types, dedup guards (regex patterns that signal distinct stories — e.g. ticker symbols, model IDs, CVE IDs), escalation budget (max LLM escalations per pipeline run)
- `sources.yaml` — feed list with priority weights 0.0-1.0, region tags, refresh intervals, parser overrides
- `prompts/`     — LLM prompts for: summarize_article, cluster_canonical_headline, cluster_narrative, extract_entities, classify_topic, why_this_matters, daily_digest, glossary_entry, explainer_article, comparison_article, beginners_guide_section, research_synthesis, social_card_text, linkedin_post, twitter_thread
- `overrides/`   — per-vertical HTML/CSS templates, theming tokens, copy

Optional:

- `tools/`       — YAML calculator/comparator/decision-tool definitions (`tools_engine.py` reads these)
- `seed_content/` — initial seed glossary entries, beginner guides, research pieces

Onboarding sequence for a new vertical:

1. Pick a name, accent colour (light + dark hex), positioning paragraph.
2. Copy `verticals/_template/` to `verticals/<name>/`.
3. Fill `config.yaml`, `sources.yaml`, prompts.
4. Validate sources fetch; prime dedup with one full pipeline run.
5. Stand up reference layer (50+ glossary entries minimum), tools (5+ minimum), 1+ research piece.
6. Apply per-property accent in `platform/shared/tokens.css`.
7. Add Caddy site config + DNS pointer.
8. Run harness; fix until score ≥ 87. Launch.
