#!/bin/sh
# Convenience wrapper: run a Postgres -> S3 backup right now, outside the cron schedule.
# This is the exact same command the cron job runs on schedule -- see docs/adr/0002, D5.
set -e
docker compose run --rm backup python3 -m app.backup
