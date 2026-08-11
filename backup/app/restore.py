"""Restores Postgres from an S3 backup. Never runs automatically -- always an explicit,
human-triggered command with a confirmation prompt unless --yes is passed. See docs/adr/0002, D6."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

import structlog

from app.config import settings
from app.pg import restore_from_file
from app.s3_client import get_client, list_backups

logger = structlog.get_logger(__name__)


def resolve_key(client, explicit_key: str | None) -> str:
    if explicit_key:
        return explicit_key
    backups = list_backups(client)
    if not backups:
        raise SystemExit(f"No backups found under s3://{settings.s3_bucket}/{settings.s3_backup_prefix}/")
    return backups[-1]["Key"]  # list_backups returns oldest-first; last is most recent


def run(key: str | None = None, yes: bool = False, confirm=input) -> int:
    if not settings.s3_bucket:
        raise SystemExit("S3_BUCKET is not configured.")

    client = get_client()
    resolved_key = resolve_key(client, key)

    if not yes:
        answer = confirm(
            f"This will DROP AND REPLACE data in database '{settings.postgres_database}' "
            f"at {settings.postgres_host} with s3://{settings.s3_bucket}/{resolved_key}. "
            "Type 'yes' to continue: "
        )
        if answer.strip().lower() != "yes":
            print("Aborted.")
            return 1

    with tempfile.TemporaryDirectory() as tmp_dir:
        dump_path = os.path.join(tmp_dir, "restore.dump")
        client.download_file(settings.s3_bucket, resolved_key, dump_path)
        logger.info("downloaded", bucket=settings.s3_bucket, key=resolved_key)

        restore_from_file(
            host=settings.postgres_host,
            port=settings.postgres_port,
            username=settings.postgres_username,
            password=settings.postgres_password,
            database=settings.postgres_database,
            in_path=dump_path,
        )
    logger.info("restore_complete", key=resolved_key)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore the Postgres database from an S3 backup.")
    parser.add_argument("--key", default=None, help="S3 object key to restore. Defaults to the most recent backup.")
    parser.add_argument("--yes", action="store_true", help="Skip the interactive confirmation prompt.")
    args = parser.parse_args()
    sys.exit(run(key=args.key, yes=args.yes))


if __name__ == "__main__":
    main()
