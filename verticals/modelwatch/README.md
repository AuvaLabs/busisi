# Modelwatch vertical

AI/ML knowledge platform — first vertical to ship (per BUILD-DIRECTIVE Phase 3).

Per-vertical files (populated in Phase 3):

- `config.yaml`  — taxonomy, entity types, dedup guards, escalation budget
- `sources.yaml` — 60-80 feeds with priority weights (AI labs 1.0, research aggregators 0.9, tech press 0.8, newsletters 0.85, indie voices 0.7, community 0.6, regulatory 0.85)
- `prompts/`     — LLM prompts: summarize_article, cluster_canonical_headline, cluster_narrative, extract_entities, classify_topic, why_this_matters, daily_digest, glossary_entry, explainer_article, comparison_article, beginners_guide_section, research_synthesis, social_card_text, linkedin_post, twitter_thread
- `overrides/`   — per-vertical templates, theming, content overrides

Design accent: warm muted amber `#B8743A` (light), `#D49464` (dark) — see `docs/design-derivation.md`.
