from pydantic import BaseModel, Field


class ClassificationResult(BaseModel):
    """Mirrors the brief's example JSON (brief §5). Produced by a single forced Claude tool
    call so the shape is schema-guaranteed rather than hoped-for from free text."""

    category: str
    spam: bool
    requires_human: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    draft_response: str | None = None


class WebhookMessage(BaseModel):
    id: int
    content: str | None = None
    message_type: str | None = None  # "incoming" | "outgoing" | "template"
    private: bool = False


class ChatwootWebhookEvent(BaseModel):
    """The subset of Chatwoot's message_created webhook payload this service cares about.
    Chatwoot sends many more fields; everything else is ignored."""

    event: str
    id: int | None = None  # message id, at the payload's top level for message_created
    content: str | None = None
    message_type: str | None = None
    private: bool = False
    conversation: dict = Field(default_factory=dict)

    @property
    def conversation_id(self) -> int | None:
        return self.conversation.get("id")

    @property
    def is_actionable_player_message(self) -> bool:
        """True only for a real, non-private message sent by the player. Excludes agent
        replies and the AI's own private notes/drafts -- see docs/ai-workflows.md#trigger."""
        return self.event == "message_created" and self.message_type == "incoming" and not self.private


class ReportData(BaseModel):
    since: str
    until: str
    total_conversations: int
    spam_count: int
    human_intervention_count: int
    categories: dict[str, int]
