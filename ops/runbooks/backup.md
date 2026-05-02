# Grimoire backup runbook

## Architecture

Two-leg backup model (mirrors atelier's pattern):

1. **Local leg** — `/srv/grimoire/ops/backup.sh` runs nightly via
   `/etc/cron.d/grimoire-backup` at 03:30 server time. Dumps Postgres
   to `/srv/grimoire/backups/postgres/dumpall-YYYYMMDD-HHMMSS.sql.gz`.
   Keeps the 14 most recent dumps locally; older ones are pruned.

2. **Off-box leg** — restic ships local dumps to Cloudflare R2 bucket
   `grimoire-backups`. Tier-A R2 keys live ONLY on the command
   center at `/home/deploy/.r2-grimoire.env` (mode 600). Driver script
   lives at `/home/deploy/grimoire/ops/scripts/r2-nightly-backup.sh`
   on the command center (TODO).

## Operator setup (one-time, required to activate R2 leg)

1. Create the R2 bucket `grimoire-backups` in the Auva Labs Cloudflare account.
2. Create an R2 API token scoped to that bucket only, IP-allowlisted to
   the command-center IPv4 + the grimoire VPS IPv4 (178.104.214.16).
3. Save access key + secret in `/home/deploy/.r2-grimoire.env` (mode
   600) on the command center, in the same shape as `~/.r2-backup.env`
   for atelier:
   ```
   R2_ACCESS_KEY_ID=...
   R2_SECRET_ACCESS_KEY=...
   R2_ACCOUNT_ID=...
   R2_BUCKET=grimoire-backups
   RESTIC_PASSWORD=<32-char random>
   RESTIC_REPOSITORY=s3:https://<ACCOUNT_ID>.r2.cloudflarestorage.com/grimoire-backups
   ```
4. Record the token's masked prefix in `~/Documents/server_credentials.txt`
   under the GRIMOIRE section.
5. Initialise the restic repo from the command center:
   `restic --repo "$RESTIC_REPOSITORY" init`.
6. Trigger a one-shot backup; verify in `/var/log/grimoire/backup.log`
   and in the R2 bucket.

## Retention policy

- **Local:** 14 daily dumps in `/srv/grimoire/backups/postgres/`.
- **R2 (when active):** 30 daily, then weekly snapshots for 1 year,
  enforced via `restic forget --prune --keep-daily 30 --keep-weekly 52`.
- **Verification:** weekly test-restore of one snapshot to a throwaway
  scratch database; `SELECT count(*)` on key tables to confirm
  integrity. Drill is automated from the command center.

## Recovery — restore latest local dump

```bash
ssh grimoire-root
cd /srv/grimoire
LATEST=$(ls -1t backups/postgres/dumpall-*.sql.gz | head -1)
echo "Restoring from $LATEST"

# Stop services that hold connections to postgres
docker compose down postgres

# Wipe and start fresh
sudo rm -rf data/postgres/*
docker compose up -d postgres
sleep 5

# Pipe the dump back in
gunzip -c "$LATEST" | docker compose exec -T postgres psql -U grimoire
```

## Recovery — restore from R2

```bash
# From the command center, where Tier-A keys live
set -a; source /home/deploy/.r2-grimoire.env; set +a
restic snapshots
restic restore latest --target /tmp/grimoire-restore
# scp the chosen dump file to grimoire, then follow the local-restore steps.
```

## Failure modes

| Failure | Mitigation |
|---|---|
| pg_dumpall fails | cron returns non-zero, log captures error, heartbeat alert fires |
| Disk fills with old dumps | retention prunes past 14 dumps; alert at /srv usage > 80% |
| R2 keys leak | bucket-scoped + IP-allowlisted; rotate immediately; restic data is encrypted at rest by RESTIC_PASSWORD so the leaked key alone cannot read snapshots |
| Restic repo corruption | `restic check`; weekly drill catches; rebuild from local 14-day window |
