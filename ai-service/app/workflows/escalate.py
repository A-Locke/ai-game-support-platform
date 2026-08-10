"""Human escalation + draft response (brief §3.D). Never sends anything to the player --
both the reasoning note and the draft are private, agent-only Chatwoot messages."""

from app import mcp_client
from app.models import ClassificationResult


async def apply_escalation(conversation_id: int, result: ClassificationResult) -> None:
    await mcp_client.call_tool(
        "create_internal_note",
        conversation_id=conversation_id,
        content=f"AI classification: {result.category} (confidence {result.confidence:.2f}). {result.reason}",
    )

    if not result.requires_human:
        return

    await mcp_client.call_tool(
        "add_conversation_tag", conversation_id=conversation_id, tags=["human-escalated"]
    )

    if result.draft_response:
        await mcp_client.call_tool(
            "create_draft_response", conversation_id=conversation_id, content=result.draft_response
        )
