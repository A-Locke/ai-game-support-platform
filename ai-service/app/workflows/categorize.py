"""Automatic categorisation (brief §3.B). The category list is configuration-driven
(app.config.settings.categories) -- this module has no hardcoded category logic beyond
writing whatever category Claude returned."""

from app import mcp_client
from app.models import ClassificationResult


async def apply_category(conversation_id: int, result: ClassificationResult) -> None:
    await mcp_client.call_tool(
        "add_conversation_tag", conversation_id=conversation_id, tags=[result.category.lower()]
    )
    await mcp_client.call_tool(
        "set_conversation_attributes",
        conversation_id=conversation_id,
        attributes={"ai_category": result.category, "ai_confidence": result.confidence},
    )
