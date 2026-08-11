# ADR 0002: Postgres Backup and Recovery

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-11 |
| **Related** | [setup.md](../setup.md#backups) · [ADR 0001](0001-architecture-and-tech-stack.md) |

## Context

Chatwoot's Postgres database is the only stateful, hard-to-regenerate data in this stack —
conversations, contacts, custom attributes, the entire support history. Everything else
(`mcp-server`, `ai-service`) is stateless (ADR 0001, D5/D6). A VM failure, a bad
`docker compose down -v`, or a botched migration would otherwise be unrecoverable data loss.
The project owner asked specifically for scheduled backups to S3, a convenient manual trigger,
and a recovery path.

## Decision Drivers

1. **Minimal moving parts**, consistent with the rest of this project's infrastructure choices.
2. **One code path for scheduled and manual runs** — a backup that only gets exercised via cron
   is a backup nobody has actually tested running.
3. **Any S3-compatible provider**, not just AWS — self-hosters commonly use Backblaze B2,
   DigitalOcean Spaces, Cloudflare R2, or a local MinIO for testing.
4. **Recovery is never automatic.** A bad automatic restore triggered by a transient failure is
   worse than no restore at all.

## Decisions

### D1: Custom-format `pg_dump` (`-Fc`) + `pg_restore`, not plain SQL + `psql`

**Decision:** Backups use `pg_dump -Fc`. Restores use `pg_restore --clean --if-exists`.

**Why:** `-Fc` is compressed by default, supports `pg_restore`'s selective/parallel restore, and
is what PostgreSQL's own documentation recommends over a plain-SQL dump for anything beyond
trivial databases. `--if-exists` specifically matters for restoring into a fresh/empty
database: without it, `--clean`'s `DROP ... ` statements for objects that don't exist yet in an
empty target are reported as errors (not fatal, but noisy and it changes `pg_restore`'s exit
code) — `--if-exists` turns those into silent no-ops, which is the common case for the disaster
recovery scenario this is actually built for (a new VM, an empty database, restore from S3).

### D2: The backup image is built on the *same* `pgvector/pgvector:pg16` base as the database

**Decision:** `backup/Dockerfile` starts `FROM pgvector/pgvector:pg16` — the identical image used
for the `postgres` service — rather than a generic Python or `postgres:16` image.

**Why:** Guarantees `pg_dump`/`pg_restore` are the exact same major version as the server
(Postgres does not support cross-major-version dumps reliably) and that the client tools
understand the `vector` extension's objects, without a second place to track version
compatibility. This mirrors the same reasoning that led to using `pgvector/pgvector:pg16` for
`postgres` itself in the first place (see PROJECT_JOURNAL.md, Milestone 1).

### D3: `boto3`, not the `aws-cli`

**Decision:** S3 upload/download/list/delete uses `boto3` directly, called from Python.

**Why:** No extra system package to install (the `aws-cli` needs either a bulky pip install or
an Alpine/Debian package that may not exist for a given base image) — `boto3` is a normal Python
dependency, consistent with this project's existing Python-first tooling (`ai-service`,
`mcp-server`, and the host-side `scripts/` are all Python). It also makes retention pruning (D7)
a few lines of Python instead of shelling out to `aws s3 rm` in a loop.

### D4: A cron daemon inside the container, not a host crontab entry

**Decision:** `backup/entrypoint.sh` writes `BACKUP_CRON_SCHEDULE` into `/etc/cron.d/backup` and
runs Debian's `cron` inside the `backup` container.

**Why:** The schedule ships as part of `docker compose up` — no separate provisioning step on
whatever VM this is deployed to, and no schedule sitting in a host crontab that isn't part of
this repo and is easy to lose when redeploying to a new machine. This is the same reasoning
brief-adjacent decisions elsewhere in this project favor (self-contained `docker compose up`
over manual host setup).

**Consequence:** cron does not inherit the container's environment variables by default — a
well-known gotcha. `entrypoint.sh` uses `declare -p $(compgen -e)` (not a naive `printenv > file`)
to snapshot the environment into a properly shell-quoted, safely re-sourceable file before the
cron job runs, so secrets containing special characters don't break the re-export.

### D5: Manual trigger and cron trigger run the literal same script

**Decision:** `scripts/backup_now.sh` runs `docker compose run --rm backup python3 -m app.backup`
— the exact command the cron job runs on schedule, not a separate "one-off" code path.

**Why:** A backup mechanism that's only ever exercised by cron, silently, is a backup nobody has
verified actually works until the day they need it. One script means the manual test run *is*
the real thing.

### D6: Recovery is a separate, always-manual command with an interactive confirmation

**Decision:** `app/restore.py` is a distinct entry point from `app/backup.py`, always requires an
explicit `docker compose run` (or `scripts/restore_from_s3.sh`) invocation, and prompts for a
typed `yes` confirmation before touching the database unless `--yes` is passed explicitly.

**Why:** Nothing in this project ever triggers a restore automatically — not a health check, not
a startup script, nothing. An automatic restore triggered by a transient failure could silently
roll back real data. The confirmation prompt exists specifically to prevent a mistyped command
from being destructive by accident; `--yes` exists for the rare case a human genuinely wants a
scripted restore (e.g. a documented, reviewed disaster-recovery runbook).

### D7: Retention pruning lives in the script, not solely in S3 bucket lifecycle rules

**Decision:** `app/backup.py` deletes S3 objects under the configured prefix older than
`BACKUP_RETENTION_DAYS` (default 14; `0` disables pruning) as its own step, using
`list_objects_v2` + `delete_objects`.

**Why:** Works identically for any S3-compatible provider — some budget/self-hosted object
stores don't support lifecycle rules at all — and keeps the entire backup lifecycle
self-contained and testable without a separate, provider-specific bucket configuration step.
Bucket lifecycle rules remain a fine complementary option for an AWS-hosted deployment
specifically; documented as optional, not required.

### D8: Backups are opt-in via configuration, not via a Compose profile

**Decision:** The `backup` service is always defined and started by default in
`docker-compose.yml`. With `S3_BUCKET` unset, `app/backup.py` logs a message and exits `0`
without attempting anything.

**Why:** Keeps `docker compose up` behavior identical to before this feature existed for anyone
who hasn't configured S3 yet — no new flag to remember. This matches how other optional-until-configured
behavior already works in this project (`MCP_ENABLE_MUTATIONS`, `AI_WEBHOOK_SHARED_SECRET`
default to a permissive/inert state rather than requiring an explicit opt-in flag). Contrast with
ADR 0003's decision to gate `ai-service` behind a Compose profile — there, *which orchestration
mode a user is in* is itself the meaningful choice being made, not a "did they configure a
secret yet" question.

## Consequences (Overall)

**Positive:** One script path for both scheduled and manual runs; works against AWS S3 or any
S3-compatible provider without code changes; the recovery story was actually built and tested,
not just assumed.

**Negative / accepted trade-offs:** If the cron daemon itself silently stops running inside the
container, backups (and pruning) silently stop too — nothing in this project alerts on a missed
backup window. Acceptable at this project's scope; a real production deployment would want an
external check (e.g. a monitoring job asserting the newest S3 object under the prefix is recent).
