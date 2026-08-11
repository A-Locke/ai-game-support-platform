#!/bin/sh
# Convenience wrapper: restore the database from an S3 backup. Interactive by default (asks
# for a typed "yes" before touching the database) -- see docs/adr/0002, D6.
#
# Usage:
#   ./scripts/restore_from_s3.sh                                 # restore the most recent backup
#   ./scripts/restore_from_s3.sh --key chatwoot-backups/chatwoot-20260811T030000Z.dump
#   ./scripts/restore_from_s3.sh --yes                            # skip the confirmation prompt
set -e
docker compose run --rm backup python3 -m app.restore "$@"
