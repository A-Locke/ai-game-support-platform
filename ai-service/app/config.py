from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for ai-service.

    This is the one component that knows both Claude and the game-support business logic
    (categories, escalation, spam). It reaches Chatwoot exclusively through mcp_server_url --
    see docs/architecture.md.
    """

    model_config = SettingsConfigDict(extra="ignore")

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    mcp_server_url: str = "http://mcp-server:8100/mcp"
    mcp_auth_token: str = ""

    ai_webhook_shared_secret: str = ""

    support_categories: str = (
        "Bug,Crash,Gameplay,Technical,Installation,Account,Performance,Billing,Feedback,Other"
    )

    game_data_dir: str = "game-data"

    log_level: str = "INFO"

    @property
    def categories(self) -> list[str]:
        return [c.strip() for c in self.support_categories.split(",") if c.strip()]


settings = Settings()
