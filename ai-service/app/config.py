from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for ai-service.

    This is the one component that knows both Claude and the support business logic
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
        "Bug,Crash,Technical,Installation,Account,Performance,Billing,Feature Request,Feedback,Other"
    )

    knowledge_base_dir: str = "knowledge-base"

    # Optional issue-tracker grounding (docs/adr/0004) -- each source is independently optional;
    # an empty *_MCP_URL means that source is skipped, not an error.
    jira_mcp_url: str = ""
    jira_mcp_api_token: str = ""
    jira_jql_project_filter: str = ""  # e.g. "project = SUPPORT" -- prepended to the search JQL
    azure_devops_mcp_url: str = ""
    azure_devops_mcp_pat: str = ""
    grounding_max_results: int = 3

    # Optional semantic search over knowledge_base_dir (docs/adr/0006). Empty rag_mcp_url means
    # ai-service falls back to knowledge.load_knowledge_excerpt()'s flat dump (ADR 0006, D7).
    rag_mcp_url: str = ""
    rag_mcp_auth_token: str = ""
    rag_top_k: int = 3

    log_level: str = "INFO"

    @property
    def categories(self) -> list[str]:
        return [c.strip() for c in self.support_categories.split(",") if c.strip()]


settings = Settings()
