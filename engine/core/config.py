"""Centralised configuration loader.

Reads environment from the process env (Docker-injected via `--env-file .env`).
Mirrors the role of ``modules/config.py`` in ThreatWatch but is multi-vertical:
per-vertical paths and config live under ``verticals/<name>/``.

All env vars have safe defaults so the module imports cleanly during tests
(no required-secret fail-import behaviour).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

# ---- Paths ----
GRIMOIRE_ROOT: Final[Path] = Path(os.environ.get("GRIMOIRE_ROOT", "/srv/grimoire"))
DATA_DIR: Final[Path] = GRIMOIRE_ROOT / "data"
STATE_DIR: Final[Path] = DATA_DIR / "state"
SNAPSHOTS_DIR: Final[Path] = DATA_DIR / "snapshots"
BACKUPS_DIR: Final[Path] = GRIMOIRE_ROOT / "backups"
VERTICALS_DIR: Final[Path] = GRIMOIRE_ROOT / "verticals"
LOG_DIR: Final[Path] = Path(os.environ.get("LOG_DIR", "/var/log/grimoire"))

# ---- LLM ----
LLM_PROVIDER: Final[str] = os.environ.get("LLM_PROVIDER", "groq")
LLM_API_KEY: Final[str] = os.environ.get("LLM_API_KEY", "")
LLM_API_KEYS: Final[list[str]] = [
    k.strip() for k in os.environ.get("LLM_API_KEYS", LLM_API_KEY).split(",") if k.strip()
]
LLM_BASE_URL: Final[str] = os.environ.get(
    "LLM_BASE_URL", "https://api.groq.com/openai/v1"
)
LLM_MODEL: Final[str] = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")
LLM_TIMEOUT: Final[float] = float(os.environ.get("LLM_TIMEOUT", "30"))
LLM_CIRCUIT_THRESHOLD: Final[int] = int(os.environ.get("LLM_CIRCUIT_THRESHOLD", "3"))
MAX_CONTENT_CHARS: Final[int] = int(os.environ.get("MAX_CONTENT_CHARS", "8000"))

# ---- Storage ----
POSTGRES_USER: Final[str] = os.environ.get("POSTGRES_USER", "grimoire")
POSTGRES_PASSWORD: Final[str] = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_DB: Final[str] = os.environ.get("POSTGRES_DB", "grimoire")
POSTGRES_HOST: Final[str] = os.environ.get("POSTGRES_HOST", "127.0.0.1")
POSTGRES_PORT: Final[int] = int(os.environ.get("POSTGRES_PORT", "5432"))
DATABASE_URL: Final[str] = os.environ.get(
    "DATABASE_URL",
    f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}",
)
REDIS_URL: Final[str] = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

# ---- Pipeline ----
FEED_CUTOFF_DAYS: Final[int] = int(os.environ.get("FEED_CUTOFF_DAYS", "7"))
MAX_FEED_FETCH_THREADS: Final[int] = int(os.environ.get("MAX_FEED_FETCH_THREADS", "16"))
MAX_SCRAPER_THREADS: Final[int] = int(os.environ.get("MAX_SCRAPER_THREADS", "16"))

# ---- Dedup ----
FUZZY_DEDUP_THRESHOLD: Final[float] = float(os.environ.get("FUZZY_DEDUP_THRESHOLD", "0.65"))
MAX_SEEN_HASHES: Final[int] = int(os.environ.get("MAX_SEEN_HASHES", "10000"))
MAX_SEEN_TITLES: Final[int] = int(os.environ.get("MAX_SEEN_TITLES", "5000"))

# ---- Handler app (Phase 9: subscribe / sponsor / tools API) ----
HANDLER_HOST: Final[str] = os.environ.get("HANDLER_HOST", "127.0.0.1")
HANDLER_PORT: Final[int] = int(os.environ.get("HANDLER_PORT", "8001"))
SUBSCRIBER_FERNET_KEY: Final[str] = os.environ.get("SUBSCRIBER_FERNET_KEY", "")
SUBSCRIBER_EMAIL_PEPPER: Final[str] = os.environ.get("SUBSCRIBER_EMAIL_PEPPER", "")
SITE_ORIGINS_RAW: Final[str] = os.environ.get("SITE_ORIGINS", "")
POSTMARK_API_TOKEN: Final[str] = os.environ.get("POSTMARK_API_TOKEN", "")
POSTMARK_FROM_ADDRESS: Final[str] = os.environ.get(
    "POSTMARK_FROM_ADDRESS", "no-reply@auvalabs.com"
)
POSTMARK_REPLY_TO: Final[str] = os.environ.get("POSTMARK_REPLY_TO", "ops@auvalabs.com")
SPONSOR_NOTIFY_TO: Final[str] = os.environ.get("SPONSOR_NOTIFY_TO", "ops@auvalabs.com")
HANDLER_RATE_LIMIT_PER_5MIN: Final[int] = int(
    os.environ.get("HANDLER_RATE_LIMIT_PER_5MIN", "10")
)

# ---- Researcher (Phase 22e) — web/scholar fetches for thin-source articles ----
# Exa.ai semantic search — empty key disables Exa and the researcher
# falls back to arXiv-only (still useful for ML/AI articles).
EXA_API_KEY: Final[str] = os.environ.get("EXA_API_KEY", "")
EXA_ENDPOINT: Final[str] = os.environ.get(
    "EXA_ENDPOINT", "https://api.exa.ai/search"
)
ARXIV_ENABLED: Final[bool] = os.environ.get("ARXIV_ENABLED", "1") not in (
    "0",
    "false",
    "False",
    "",
)
ARXIV_ENDPOINT: Final[str] = os.environ.get(
    "ARXIV_ENDPOINT", "https://export.arxiv.org/api/query"
)
# Wikipedia search — free, keyless, no daily cap. Returns title +
# extract (intro paragraph) per result. Especially useful for "history,
# regulation, comparable cases, expert commentary" expansion (what the
# F2 prompt explicitly asks bundles for).
WIKIPEDIA_ENABLED: Final[bool] = os.environ.get("WIKIPEDIA_ENABLED", "1") not in (
    "0",
    "false",
    "False",
    "",
)
WIKIPEDIA_ENDPOINT: Final[str] = os.environ.get(
    "WIKIPEDIA_ENDPOINT", "https://en.wikipedia.org/w/api.php"
)
RESEARCH_MAX_PER_TICK: Final[int] = int(
    os.environ.get("RESEARCH_MAX_PER_TICK", "5")
)
RESEARCH_QUERY_TIMEOUT: Final[float] = float(
    os.environ.get("RESEARCH_QUERY_TIMEOUT", "10")
)
RESEARCH_BUNDLE_SIZE: Final[int] = int(
    os.environ.get("RESEARCH_BUNDLE_SIZE", "10")
)
# Researcher cache (Phase 22h): cache search-provider responses in Redis
# so re-runs against the same article (or shared-query articles) avoid
# re-paying. TTL governs staleness — 7 days is the default because the
# stories researcher cares about move on a 1-2 week news cycle.
RESEARCH_CACHE_TTL_DAYS: Final[int] = int(
    os.environ.get("RESEARCH_CACHE_TTL_DAYS", "7")
)
# Hard daily ceiling on Exa.ai calls (the paid provider). 0 disables the
# cap. The cap is enforced via a Redis day-keyed counter so multiple
# pipeline ticks share the same budget.
EXA_DAILY_CAP: Final[int] = int(os.environ.get("EXA_DAILY_CAP", "200"))

# ---- Logging ----
LOG_LEVEL: Final[str] = os.environ.get("LOG_LEVEL", "INFO")


def site_origins() -> dict[str, str]:
    """Parse ``SITE_ORIGINS`` env (``"vertical=origin,…"``) into a dict.

    Malformed chunks are dropped silently so the handler still boots in dev.
    """
    out: dict[str, str] = {}
    for chunk in SITE_ORIGINS_RAW.split(","):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, origin = chunk.split("=", 1)
        name = name.strip()
        origin = origin.strip().rstrip("/")
        if name and origin:
            out[name] = origin
    return out


def vertical_dir(vertical_id: str) -> Path:
    """Return the directory for a given vertical (e.g. modelwatch)."""
    if "/" in vertical_id or vertical_id.startswith("."):
        raise ValueError(f"Invalid vertical_id: {vertical_id!r}")
    return VERTICALS_DIR / vertical_id


def canonical_base_for(vertical_name: str) -> str:
    """Return the canonical base URL for a vertical (no trailing slash).

    Env override key is ``<VERTICAL>_CANONICAL_BASE`` (e.g.
    ``MODELWATCH_CANONICAL_BASE=https://modelwatch.com``). Unset →
    placeholder ``http://<vertical>.local`` for local dev / pre-domain.
    Domain commit is therefore a one-line ``.env`` change, not a code
    edit.
    """
    if "/" in vertical_name or vertical_name.startswith("."):
        raise ValueError(f"Invalid vertical name: {vertical_name!r}")
    env_key = f"{vertical_name.upper()}_CANONICAL_BASE"
    base = os.environ.get(env_key, "").strip().rstrip("/")
    return base or f"http://{vertical_name}.local"


def validate_required(*, llm: bool = True, postgres: bool = True) -> list[str]:
    """Return a list of missing required envs. Empty list = OK to proceed.

    Callers decide whether missing envs are fatal (production) or fine
    (tests, local dev). The function never raises.
    """
    missing: list[str] = []
    if llm and not LLM_API_KEY and not LLM_API_KEYS:
        missing.append("LLM_API_KEY or LLM_API_KEYS")
    if postgres and not POSTGRES_PASSWORD:
        missing.append("POSTGRES_PASSWORD")
    return missing
