from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for rag-mcp. See docs/adr/0006."""

    model_config = SettingsConfigDict(env_prefix="RAG_", extra="ignore")

    postgres_host: str = "postgres"
    postgres_port: str = "5432"
    postgres_username: str = "postgres"
    postgres_password: str = ""
    postgres_database: str = "chatwoot"
    schema_name: str = "rag"

    knowledge_base_dir: str = "knowledge-base"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    default_top_k: int = 3

    auth_token: str = ""
    transport: str = "stdio"
    http_host: str = "0.0.0.0"
    http_port: int = 8200

    # Ingestion UI (docs/adr/0007) -- a separate credential from auth_token above, since the
    # audience is different (a human in a browser, not a service presenting a bearer token).
    # Fails closed like everything else here: an unset ui_password means the UI refuses to serve.
    ui_username: str = "admin"
    ui_password: str = ""

    log_level: str = "INFO"


settings = Settings()
