import boto3
import pytest
from moto import mock_aws

from app.config import settings


@pytest.fixture(autouse=True)
def configured_settings():
    settings.s3_bucket = "test-backups-bucket"
    settings.s3_region = "us-east-1"
    settings.s3_endpoint_url = ""
    settings.s3_access_key_id = ""
    settings.s3_secret_access_key = ""
    settings.s3_backup_prefix = "chatwoot-backups"
    settings.backup_retention_days = 14
    settings.postgres_host = "postgres.test"
    settings.postgres_port = "5432"
    settings.postgres_username = "postgres"
    settings.postgres_password = "test-password"
    settings.postgres_database = "chatwoot"
    yield


@pytest.fixture
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="test-backups-bucket")
        yield client
