# Database migrations runbook

Schema changes for grimoire run through alembic. Config:

  * `alembic.ini` — repo root
  * `ops/migrations/env.py` — reads DATABASE_URL from `engine.core.config`
  * `ops/migrations/versions/` — revision files (`0001_baseline.py`, …)

Production was stamped to revision `0001` (baseline) on launch — that
revision's `upgrade()` is `Base.metadata.create_all`, so re-running it is
a no-op against the existing DB.

## Day-to-day workflow

```bash
# from /srv/grimoire on the server, or repo root locally:
source .venv/bin/activate
set -a; source .env; set +a   # exports DATABASE_URL etc.

# inspect current head
alembic current

# inspect available history
alembic history

# generate a new revision after editing engine/core/db.py
alembic revision --autogenerate -m "add foo column on articles"

# review the generated file under ops/migrations/versions/, then apply:
alembic upgrade head

# rollback the most recent revision (rare)
alembic downgrade -1
```

## Fresh deploy on a new database

```bash
# create the DB + role first (psql), then:
alembic upgrade head     # runs every revision in order
```

## Rebasing onto an existing prod DB (e.g. cloning to a new server)

If a prod DB already has the schema (e.g. from `Base.metadata.create_all`
in some legacy path), stamp it instead of running migrations:

```bash
alembic stamp head
```

## Caveats

- Always review `--autogenerate` output before committing — alembic can
  miss server-side defaults, custom check constraints, partial indexes,
  and Postgres-specific types.
- Never edit a revision file that has already been applied in prod.
  Create a new forward revision instead.
- Migrations run inside a single transaction by default; for large data
  backfills, split into a schema migration + a separate data-fill script
  invoked from a cron tick.
