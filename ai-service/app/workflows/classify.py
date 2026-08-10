"""Orchestrates the shared classification call and dispatches to the spam / categorize /
escalate workflows. See docs/ai-workflows.md for the full flow and idempotency design."""

import structlog

from app import mcp_client
from app.claude_client import classify_conversation
from app.mcp_client import MCPToolError
from app.workflows.categorize import apply_category
from app.workflows.escalate import apply_escalation
from app.workflows.spam import apply_spam

logger = structlog.get_logger(__name__)

IDEMPOTENCY_ATTRIBUTE = "ai_last_processed_message_id"


async def _extract_player_messages(conversation_id: int) -> list[str]:
    payload = await mcp_client.call_tool("get_conversation_messages", conversation_id=conversation_id)
    messages = payload.get("payload", payload if isinstance(payload, list) else [])
    return [
        m["content"]
        for m in messages
        if isinstance(m, dict) and m.get("message_type") == "incoming" and not m.get("private") and m.get("content")
    ]


async def process_incoming_message(conversation_id: int, message_id: int) -> dict:
    """Entry point called by the webhook handler for every actionable player message."""
    try:
        conversation = await mcp_client.call_tool("get_conversation", conversation_id=conversation_id)
    except MCPToolError as exc:
        logger.error("mcp_unreachable", conversation_id=conversation_id, error=str(exc))
        return {"status": "error", "reason": "mcp_unreachable"}

    already_processed = conversation.get("custom_attributes", {}).get(IDEMPOTENCY_ATTRIBUTE)
    if already_processed == str(message_id):
        logger.info("skipped_duplicate_event", conversation_id=conversation_id, message_id=message_id)
        return {"status": "skipped", "reason": "already_processed"}

    try:
        player_messages = await _extract_player_messages(conversation_id)
        result = await classify_conversation(player_messages)

        if result.spam:
            await apply_spam(conversation_id, result)
        else:
            await apply_category(conversation_id, result)

        await apply_escalation(conversation_id, result)

        await mcp_client.call_tool(
            "set_conversation_attributes",
            conversation_id=conversation_id,
            attributes={IDEMPOTENCY_ATTRIBUTE: str(message_id)},
        )
    except MCPToolError as exc:
        # Logged, not raised further -- the webhook handler always returns 200 to Chatwoot
        # regardless (see docs/ai-workflows.md's error handling section) so a transient MCP
        # failure doesn't cause Chatwoot to retry-storm an otherwise-successful delivery.
        logger.error("workflow_mcp_failure", conversation_id=conversation_id, error=str(exc))
        return {"status": "error", "reason": "mcp_tool_failure"}

    logger.info(
        "processed_conversation",
        conversation_id=conversation_id,
        category=result.category,
        spam=result.spam,
        requires_human=result.requires_human,
    )
    return {"status": "processed", "category": result.category, "spam": result.spam, "requires_human": result.requires_human}
