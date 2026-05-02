"""Vertical-agnostic engine modules.

All modules in this package are tenant-neutral: they accept a `vertical_id`
parameter (or load per-vertical config from `verticals/<name>/`) but contain
no vertical-specific logic.

See ``docs/architecture-derivation.md`` §11 for the canonical module list and
port plan from ThreatWatch.
"""
