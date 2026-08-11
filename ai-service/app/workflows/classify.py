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


INCOMING_MESSAGE_TYPES = ("incoming", 0)  # Chatwoot's Application API returns the raw integer
# enum (0); webhook payloads separately serialize it as the string "incoming" (see
# app.models.ChatwootWebhookEvent). get_conversation_messages goes through the former path --
# found live when a real message never matched this filter because it was compared as a string.


async def get_incoming_messages(conversation_id: int) -> list[dict]:
    """Real customer messages only -- excludes agent replies and the AI's own private notes.
    Shared by the classification prompt builder below and by app.cli's batch sweep, which needs
    the latest genuine customer message id (not "the conversation's last message", which is
    often one of this workflow's own notes -- see docs/adr/0003, D3 and PROJECT_JOURNAL.md,
    Milestone 5)."""
    payload = await mcp_client.call_tool("get_conversation_messages", conversation_id=conversation_id)
    messages = payload.get("payload", payload if isinstance(payload, list) else [])
    return [
        m
        for m in messages
        if isinstance(m, dict) and m.get("message_type") in INCOMING_MESSAGE_TYPES and not m.get("private")
    ]


async def _extract_player_messages(conversation_id: int) -> list[str]:
    messages = await get_incoming_messages(conversation_id)
    return [m["content"] for m in messages if m.get("content")]


async def process_incoming_message(conversation_id: int, message_id: int) -> dict:
    """Entry point called by the webhook handler for every actionable customer message."""
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
