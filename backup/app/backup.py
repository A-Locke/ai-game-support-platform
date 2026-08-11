"""Dumps Postgres and uploads to S3. The exact same entry point runs on the cron schedule and
via a manual one-off `docker compose run --rm backup python3 -m app.backup` -- see
docs/adr/0002, D5. Silently a no-op if S3_BUCKET isn't configured (D8)."""

from __future__ import annotations

import datetime
import os
import sys
import tempfile

import structlog

from app.config import settings
from app.pg import dump_to_file
from app.s3_client import get_client, list_backups

logger = structlog.get_logger(__name__)


def run() -> int:
    if not settings.s3_bucket:
        logger.warning("s3_not_configured", detail="S3_BUCKET is empty -- skipping backup")
        return 0

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"{settings.s3_backup_prefix}/{settings.postgres_database}-{timestamp}.dump"

    client = get_client()

    with tempfile.TemporaryDirectory() as tmp_dir:
        dump_path = os.path.join(tmp_dir, "backup.dump")
        dump_to_file(
            host=settings.postgres_host,
            port=settings.postgres_port,
            username=settings.postgres_username,
            password=settings.postgres_password,
            database=settings.postgres_database,
            out_path=dump_path,
        )
        size_mb = os.path.getsize(dump_path) / 1e6
        logger.info("dump_complete", path=dump_path, size_mb=round(size_mb, 1))

        client.upload_file(dump_path, settings.s3_bucket, key)
        logger.info("uploaded", bucket=settings.s3_bucket, key=key)

    _prune_old_backups(client)
    return 0


def _prune_old_backups(client) -> None:
    if settings.backup_retention_days <= 0:
        return
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=settings.backup_retention_days
    )
    old = [o for o in list_backups(client) if o["LastModified"] < cutoff]
    if not old:
        return
    client.delete_objects(
        Bucket=settings.s3_bucket, Delete={"Objects": [{"Key": o["Key"]} for o in old]}
    )
    logger.info("pruned_old_backups", count=len(old), retention_days=settings.backup_retention_days)


if __name__ == "__main__":
    sys.exit(run())
