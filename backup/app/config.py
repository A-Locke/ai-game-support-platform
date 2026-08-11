from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the backup/restore service. See docs/adr/0002 for why backups
    are opt-in via configuration (empty S3_BUCKET = inert) rather than a Compose profile."""

    model_config = SettingsConfigDict(extra="ignore")

    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = ""  # only needed for non-AWS S3-compatible providers
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_backup_prefix: str = "chatwoot-backups"
    backup_retention_days: int = 14

    postgres_host: str = "postgres"
    postgres_port: str = "5432"
    postgres_username: str = "postgres"
    postgres_password: str = ""
    postgres_database: str = "chatwoot"

    log_level: str = "INFO"


settings = Settings()
