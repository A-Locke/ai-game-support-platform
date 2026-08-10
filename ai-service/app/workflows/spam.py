"""Spam detection (brief §3.A). Spam is tagged and moved out of the active queue -- never
deleted, so a human can always correct a false positive."""

from app import mcp_client
from app.models import ClassificationResult


async def apply_spam(conversation_id: int, result: ClassificationResult) -> None:
    await mcp_client.call_tool("add_conversation_tag", conversation_id=conversation_id, tags=["spam"])
    await mcp_client.call_tool(
        "set_conversation_attributes",
        conversation_id=conversation_id,
        attributes={"ai_category": "Spam", "ai_confidence": result.confidence},
    )
    await mcp_client.call_tool("update_conversation_status", conversation_id=conversation_id, status="pending")
