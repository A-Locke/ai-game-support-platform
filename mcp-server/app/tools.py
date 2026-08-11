"""The MCP tool surface: a small, curated abstraction over Chatwoot.

Every tool here is plain Chatwoot business logic -- nothing about Claude,
prompts, or "AI decisions" belongs in this file. That separation is what lets
the AI orchestration layer, or any other MCP client, use this server without
this server knowing or caring who's calling it.

Read-only tools work regardless of configuration. Mutating tools (anything
that changes Chatwoot state) check `settings.enable_mutations` first, so a
deployment can be locked into a read-only/reporting mode without a code change.
"""

from __future__ import annotations

from functools import lru_cache

from fastmcp import FastMCP

from app.chatwoot_client import ChatwootAPIError, ChatwootClient
from app.config import settings

mcp = FastMCP(
    name="support-mcp-server",
    instructions=(
        "Curated Chatwoot support operations. Read-only tools (get_conversation, "
        "search_conversations, get_conversation_messages, search_contacts, "
        "get_support_statistics, get_category_statistics) are always available. "
        "Mutating tools (update_conversation_status, add_conversation_tag, "
        "set_conversation_attributes, create_internal_note, create_draft_response) change "
        "Chatwoot state and can be disabled deployment-wide via MCP_ENABLE_MUTATIONS. "
        "create_draft_response never sends anything to a customer -- it stores a private, "
        "agent-only note. No tool here sends a message a customer will see."
    ),
)


@lru_cache
def get_client() -> ChatwootClient:
    return ChatwootClient(
        base_url=settings.chatwoot_base_url,
        account_id=settings.chatwoot_account_id,
        api_access_token=settings.chatwoot_api_access_token,
    )


def _error(exc: ChatwootAPIError) -> dict:
    return {"error": True, "status_code": exc.status_code, "detail": exc.detail}


def _mutation_guard() -> dict | None:
    if not settings.enable_mutations:
        return {"error": True, "detail": "Mutating operations are disabled on this MCP server"}
    return None


# -- Read-only tools -----------------------------------------------------------


@mcp.tool()
async def get_conversation(conversation_id: int) -> dict:
    """Fetch a single Chatwoot conversation by id, including status, contact and custom attributes."""
    try:
        return await get_client().get_conversation(conversation_id)
    except ChatwootAPIError as exc:
        return _error(exc)


@mcp.tool()
async def search_conversations(query: str | None = None, status: str | None = None, page: int = 1) -> dict:
    """Search or list conversations, optionally filtered by free-text query and/or status."""
    try:
        return await get_client().search_conversations(query=query, status=status, page=page)
    except ChatwootAPIError as exc:
        return _error(exc)


@mcp.tool()
async def get_conversation_messages(conversation_id: int) -> dict:
    """Fetch the full message history (customer + agent + notes) for a conversation."""
    try:
        return await get_client().get_conversation_messages(conversation_id)
    except ChatwootAPIError as exc:
        return _error(exc)


@mcp.tool()
async def search_contacts(query: str) -> dict:
    """Search Chatwoot contacts (customers) by name, email, or identifier."""
    try:
        return await get_client().search_contacts(query)
    except ChatwootAPIError as exc:
        return _error(exc)


def _date_range_conditions(since: str, until: str, *extra: dict) -> list[dict]:
    """Build a Chatwoot filter condition list with correct query_operator placement.

    Chatwoot's filter API treats query_operator as the joiner between condition i and i+1, not
    a per-condition flag -- it must be set on every condition except the last, or the generated
    SQL is missing an AND/OR between two of the WHERE clauses and Chatwoot 500s with a
    PG::SyntaxError. Found live: get_category_statistics appends a third (label) condition to a
    two-condition base that only had query_operator on its first entry, leaving conditions 2
    and 3 unjoined. See PROJECT_JOURNAL.md, Milestone 2.
    """
    conditions = [
        {"attribute_key": "created_at", "filter_operator": "is_greater_than", "values": [since]},
        {"attribute_key": "created_at", "filter_operator": "is_less_than", "values": [until]},
        *extra,
    ]
    for condition in conditions[:-1]:
        condition["query_operator"] = "and"
    return conditions


@mcp.tool()
async def get_support_statistics(since: str, until: str) -> dict:
    """Aggregate ticket volume statistics for a date range (ISO 8601 dates, e.g. "2026-08-01").

    Returns total conversation count, counts per status, spam count (via the
    "spam" label) and human-intervention count (via the "human-escalated"
    label). This is data retrieval only -- no summarisation happens here.
    """
    client = get_client()
    try:
        total = await client.filter_conversations(_date_range_conditions(since, until))
        spam = await client.filter_conversations(
            _date_range_conditions(
                since, until, {"attribute_key": "labels", "filter_operator": "equal_to", "values": ["spam"]}
            )
        )
        escalated = await client.filter_conversations(
            _date_range_conditions(
                since,
                until,
                {"attribute_key": "labels", "filter_operator": "equal_to", "values": ["human-escalated"]},
            )
        )
    except ChatwootAPIError as exc:
        return _error(exc)

    return {
        "since": since,
        "until": until,
        "total_conversations": total.get("meta", {}).get("all_count", len(total.get("payload", []))),
        "spam_count": spam.get("meta", {}).get("all_count", len(spam.get("payload", []))),
        "human_intervention_count": escalated.get("meta", {}).get(
            "all_count", len(escalated.get("payload", []))
        ),
    }


@mcp.tool()
async def get_category_statistics(since: str, until: str, categories: list[str]) -> dict:
    """Count conversations per category label for a date range.

    `categories` is supplied by the caller (the AI service owns the
    configurable category list) so this server has no hardcoded notion of
    what a "category" is -- categories are just Chatwoot labels to it.
    """
    client = get_client()
    counts: dict[str, int] = {}
    try:
        for category in categories:
            result = await client.filter_conversations(
                _date_range_conditions(
                    since,
                    until,
                    {"attribute_key": "labels", "filter_operator": "equal_to", "values": [category.lower()]},
                )
            )
            counts[category] = result.get("meta", {}).get("all_count", len(result.get("payload", [])))
    except ChatwootAPIError as exc:
        return _error(exc)

    return {"since": since, "until": until, "categories": counts}


# -- Mutating tools --------------------------------------------------------------


@mcp.tool()
async def update_conversation_status(conversation_id: int, status: str) -> dict:
    """Change a conversation's status. One of: open, resolved, pending, snoozed."""
    if guard := _mutation_guard():
        return guard
    if status not in {"open", "resolved", "pending", "snoozed"}:
        return {"error": True, "detail": f"invalid status: {status}"}
    try:
        return await get_client().update_conversation_status(conversation_id, status)
    except ChatwootAPIError as exc:
        return _error(exc)


@mcp.tool()
async def add_conversation_tag(conversation_id: int, tags: list[str]) -> dict:
    """Attach one or more labels/tags to a conversation (e.g. category or "spam")."""
    if guard := _mutation_guard():
        return guard
    try:
        return await get_client().add_conversation_labels(conversation_id, tags)
    except ChatwootAPIError as exc:
        return _error(exc)


@mcp.tool()
async def set_conversation_attributes(conversation_id: int, attributes: dict[str, str | float | bool]) -> dict:
    """Set custom attributes on a conversation (e.g. ai_category: str, ai_confidence: float).

    Chatwoot custom attributes can be text, number, or boolean -- dict[str, str] was too
    narrow and rejected a real ai_confidence float from ai-service in live testing (a
    cross-service contract mismatch neither side's own unit tests could catch on their own).
    See PROJECT_JOURNAL.md, Milestone 2.
    """
    if guard := _mutation_guard():
        return guard
    try:
        return await get_client().set_conversation_attributes(conversation_id, attributes)
    except ChatwootAPIError as exc:
        return _error(exc)


@mcp.tool()
async def create_internal_note(conversation_id: int, content: str) -> dict:
    """Add a private note to a conversation, visible only to agents (e.g. AI classification reasoning)."""
    if guard := _mutation_guard():
        return guard
    try:
        return await get_client().create_private_note(conversation_id, content)
    except ChatwootAPIError as exc:
        return _error(exc)


@mcp.tool()
async def create_draft_response(conversation_id: int, content: str) -> dict:
    """Store a suggested customer-facing reply as a private note tagged "ai-draft".

    This never sends anything to the customer. The draft is only visible to
    agents inside Chatwoot's conversation panel until a human copies it into
    a real reply.
    """
    if guard := _mutation_guard():
        return guard
    try:
        client = get_client()
        note = await client.create_private_note(conversation_id, f"[AI DRAFT]\n\n{content}")
        await client.add_conversation_labels(conversation_id, ["ai-draft"])
        return note
    except ChatwootAPIError as exc:
        return _error(exc)
