# Grimoire backup runbook

## Architecture

Two-leg backup model:

1. **Local leg** — `/srv/grimoire/ops/backup.sh` runs nightly via
   `/etc/cron.d/grimoire-backup` at 03:30 server time. Dumps Postgres
   to `/srv/grimoire/backups/postgres/dumpall-YYYYMMDD-HHMMSS.sql.gz`.
   Keeps the 14 most recent dumps locally; older ones are pruned.

2. **R2 push leg** — same `backup.sh` invocation pushes the freshly-
   written dump to Cloudflare R2 bucket `grimoire-backups` via the
   AWS S3-compatible API (`aws s3 cp` with `--endpoint-url`). Activates
   only when `AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY` are exported
   in `/srv/grimoire/.env`; otherwise the step is skipped silently and
   the local dump still happens.

## Operator setup (one-time, required to activate R2 leg)

1. R2 bucket `grimoire-backups` is provisioned (CF account
   `22fe4279ad540a78456e6e4c82e62a1f`, endpoint
   `https://22fe4279ad540a78456e6e4c82e62a1f.r2.cloudflarestorage.com`).
2. In Cloudflare dash → R2 → Manage R2 API Tokens, create a token scoped
   read+write to **bucket `grimoire-backups` only**. (Optional but
   recommended: IP-allowlist the grimoire VPS IPv4 only —
   178.104.214.16.)
3. Append the access key + secret to `/srv/grimoire/.env` on the VPS
   (mode 600, root-owned). The shape:
   ```
   AWS_ACCESS_KEY_ID=...
   AWS_SECRET_ACCESS_KEY=...
   # Optional overrides (defaults match the live bucket):
   # R2_BUCKET=grimoire-backups
   # R2_ENDPOINT=https://22fe4279ad540a78456e6e4c82e62a1f.r2.cloudflarestorage.com
   ```
4. Record the access-key prefix + creation date in
   `~/kb_center/server_credentials.md` under the GRIMOIRE section.
   The full secret stays only in `/srv/grimoire/.env` and the
   command-center master record.
5. Install the AWS CLI on the VPS if not already present:
   `apt-get install -y awscli` (Ubuntu) — backup.sh skips the R2 push
   gracefully when `aws` is missing.
6. Trigger a one-shot backup: `sudo /srv/grimoire/ops/backup.sh`. Verify:
   ```
   tail -20 /var/log/grimoire/backup.log     # expect "R2 push ok"
   aws --endpoint-url https://22fe4279ad540a78456e6e4c82e62a1f.r2.cloudflarestorage.com \
     s3 ls s3://grimoire-backups/postgres/   # latest dump should be listed
   ```

## Retention policy

- **Local:** 14 dumps in `/srv/grimoire/backups/postgres/` (one per
  cron tick), pruned by `backup.sh` itself.
- **R2:** unlimited at the script level — every push is a new key
  under `s3://grimoire-backups/postgres/dumpall-YYYYMMDD-HHMMSS.sql.gz`.
  Bucket-side lifecycle rules (configure in CF dash → R2 → Lifecycle)
  should expire objects older than 365 days to keep R2 storage costs
  bounded. R2 has zero egress so restore reads are free.
- **Verification:** monthly test-restore of one snapshot to a throwaway
  scratch database; `SELECT count(*)` on key tables to confirm
  integrity.

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
# From the command center (or any box with the access key in env):
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
ENDPOINT=https://22fe4279ad540a78456e6e4c82e62a1f.r2.cloudflarestorage.com

# List available dumps (newest last):
aws --endpoint-url "$ENDPOINT" s3 ls s3://grimoire-backups/postgres/

# Download the chosen dump:
aws --endpoint-url "$ENDPOINT" s3 cp \
  s3://grimoire-backups/postgres/dumpall-20260505-033000.sql.gz \
  /tmp/grimoire-restore.sql.gz

# scp it to the grimoire VPS and run the "restore latest local dump"
# steps above against the downloaded file.
```

## Failure modes

| Failure | Mitigation |
|---|---|
| pg_dumpall fails | cron returns non-zero, log captures error, heartbeat alert fires; `set -uo pipefail` (not `-e`) so R2 push is still attempted |
| Disk fills with old dumps | retention prunes past 14 dumps; alert at /srv usage > 80% |
| R2 push fails | local dump is intact; log records "R2 push FAILED"; next tick retries (idempotent — every push is a uniquely-named key) |
| R2 keys leak | bucket-scoped (and ideally IP-allowlisted); rotate via CF dash; old objects remain readable for any holder of the new key |
| Bucket lifecycle deletes too aggressively | tighten the bucket lifecycle rule in CF dash; local 14-day window provides short-term recovery while restore-from-R2 is unavailable |
