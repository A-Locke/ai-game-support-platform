"""boto3 S3 client factory + list helper, shared between backup.py and restore.py. Works
against AWS S3 or any S3-compatible provider via S3_ENDPOINT_URL -- see docs/adr/0002, D3/D7."""

from __future__ import annotations

import boto3

from app.config import settings


def get_client():
    kwargs: dict = {"region_name": settings.s3_region}
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    if settings.s3_access_key_id:
        kwargs["aws_access_key_id"] = settings.s3_access_key_id
        kwargs["aws_secret_access_key"] = settings.s3_secret_access_key
    return boto3.client("s3", **kwargs)


def list_backups(client) -> list[dict]:
    """All backup objects under the configured prefix, oldest first."""
    paginator = client.get_paginator("list_objects_v2")
    objects: list[dict] = []
    for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=f"{settings.s3_backup_prefix}/"):
        objects.extend(page.get("Contents", []))
    return sorted(objects, key=lambda o: o["LastModified"])
