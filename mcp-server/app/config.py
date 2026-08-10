from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the support MCP server.

    All values are supplied via environment variables (see .env.example at the
    repo root). Nothing here is Claude-specific -- this server has no idea an
    LLM exists on the other end of the MCP connection.
    """

    model_config = SettingsConfigDict(env_prefix="MCP_", extra="ignore")

    chatwoot_base_url: str = "http://chatwoot:3000"
    chatwoot_account_id: int = 1
    chatwoot_api_access_token: str = ""

    # Bearer token that MCP clients (the ai-service) must present when talking
    # to this server over Streamable HTTP. Not required for local stdio use,
    # since that transport only ever runs as a trusted child process.
    auth_token: str = ""

    # Feature flag separating read-only tools from mutating ones. Turning this
    # off leaves every read tool available but disables tag/attribute/note
    # writes -- useful for a read-only demo or a locked-down deployment.
    enable_mutations: bool = True

    transport: str = "stdio"  # "stdio" or "http"
    http_host: str = "0.0.0.0"
    http_port: int = 8100

    log_level: str = "INFO"


settings = Settings()
