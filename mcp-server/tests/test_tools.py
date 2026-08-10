import respx
from httpx import Response

from app.tools import mcp


async def test_tool_discovery_lists_expected_tools():
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert {
        "get_conversation",
        "search_conversations",
        "get_conversation_messages",
        "search_contacts",
        "get_support_statistics",
        "get_category_statistics",
        "update_conversation_status",
        "add_conversation_tag",
        "set_conversation_attributes",
        "create_internal_note",
        "create_draft_response",
    } <= names


@respx.mock
async def test_get_conversation_valid_call_returns_chatwoot_payload():
    respx.get("http://chatwoot.test/api/v1/accounts/1/conversations/42").mock(
        return_value=Response(200, json={"id": 42, "status": "open"})
    )

    result = await mcp.call_tool("get_conversation", {"conversation_id": 42})

    assert result.structured_content == {"id": 42, "status": "open"}
    assert not result.is_error


@respx.mock
async def test_add_conversation_tag_valid_call():
    respx.get("http://chatwoot.test/api/v1/accounts/1/conversations/42/labels").mock(
        return_value=Response(200, json={"payload": []})
    )
    respx.post("http://chatwoot.test/api/v1/accounts/1/conversations/42/labels").mock(
        return_value=Response(200, json={"payload": ["bug"]})
    )

    result = await mcp.call_tool("add_conversation_tag", {"conversation_id": 42, "tags": ["bug"]})

    assert result.structured_content == {"payload": ["bug"]}


@respx.mock
async def test_add_conversation_tag_merges_with_existing_labels():
    # Regression test: found live -- Chatwoot's labels endpoint replaces the full label set
    # rather than adding to it. A second add_conversation_tag call for a different label must
    # not drop the first one.
    respx.get("http://chatwoot.test/api/v1/accounts/1/conversations/42/labels").mock(
        return_value=Response(200, json={"payload": ["crash"]})
    )
    post_route = respx.post("http://chatwoot.test/api/v1/accounts/1/conversations/42/labels").mock(
        return_value=Response(200, json={"payload": ["crash", "human-escalated"]})
    )

    await mcp.call_tool("add_conversation_tag", {"conversation_id": 42, "tags": ["human-escalated"]})

    import json

    sent_body = json.loads(post_route.calls.last.request.content)
    assert sorted(sent_body["labels"]) == ["crash", "human-escalated"]


@respx.mock
async def test_set_conversation_attributes_accepts_mixed_value_types():
    # Regression test: found live -- ai-service sends a float (ai_confidence) alongside a
    # string (ai_category) in the same call. dict[str, str] rejected the float.
    route = respx.post("http://chatwoot.test/api/v1/accounts/1/conversations/42/custom_attributes").mock(
        return_value=Response(200, json={"custom_attributes": {"ai_category": "Bug", "ai_confidence": 0.94}})
    )

    result = await mcp.call_tool(
        "set_conversation_attributes",
        {"conversation_id": 42, "attributes": {"ai_category": "Bug", "ai_confidence": 0.94}},
    )

    assert not result.is_error
    assert route.called


async def test_invalid_arguments_raise_validation_error():
    from fastmcp.exceptions import ValidationError

    import pytest

    with pytest.raises(ValidationError):
        await mcp.call_tool("get_conversation", {"conversation_id": "not-an-int"})


@respx.mock
async def test_chatwoot_api_failure_returns_structured_error_not_a_crash():
    respx.get("http://chatwoot.test/api/v1/accounts/1/conversations/99").mock(
        return_value=Response(500, text="internal server error")
    )

    result = await mcp.call_tool("get_conversation", {"conversation_id": 99})

    assert result.structured_content["error"] is True
    assert result.structured_content["status_code"] == 500


async def test_mutations_disabled_short_circuits_write_tools():
    from app.config import settings

    settings.enable_mutations = False
    try:
        result = await mcp.call_tool("create_internal_note", {"conversation_id": 1, "content": "hi"})
        assert result.structured_content["error"] is True
        assert "disabled" in result.structured_content["detail"]
    finally:
        settings.enable_mutations = True


@respx.mock
async def test_create_draft_response_stores_private_note_and_tags_it():
    note_route = respx.post("http://chatwoot.test/api/v1/accounts/1/conversations/7/messages").mock(
        return_value=Response(200, json={"id": 501, "private": True})
    )
    respx.get("http://chatwoot.test/api/v1/accounts/1/conversations/7/labels").mock(
        return_value=Response(200, json={"payload": ["crash", "human-escalated"]})
    )
    label_route = respx.post("http://chatwoot.test/api/v1/accounts/1/conversations/7/labels").mock(
        return_value=Response(200, json={"payload": ["ai-draft", "crash", "human-escalated"]})
    )

    result = await mcp.call_tool(
        "create_draft_response", {"conversation_id": 7, "content": "Thanks for reporting!"}
    )

    assert result.structured_content == {"id": 501, "private": True}
    sent_body = note_route.calls.last.request.content.decode()
    assert "[AI DRAFT]" in sent_body
    assert "Thanks for reporting!" in sent_body
    assert label_route.called
    import json

    sent_labels = json.loads(label_route.calls.last.request.content)["labels"]
    assert sorted(sent_labels) == ["ai-draft", "crash", "human-escalated"]


@respx.mock
async def test_get_support_statistics_aggregates_filtered_counts():
    route = respx.post("http://chatwoot.test/api/v1/accounts/1/conversations/filter").mock(
        return_value=Response(200, json={"payload": [], "meta": {"all_count": 3}})
    )

    result = await mcp.call_tool(
        "get_support_statistics", {"since": "2026-08-01", "until": "2026-08-10"}
    )

    assert result.structured_content == {
        "since": "2026-08-01",
        "until": "2026-08-10",
        "total_conversations": 3,
        "spam_count": 3,
        "human_intervention_count": 3,
    }
    assert route.call_count == 3


@respx.mock
async def test_get_category_statistics_sets_query_operator_on_every_condition_but_last():
    # Regression test: found live -- a 3-condition filter (date >, date <, label) 500'd with a
    # Postgres syntax error because query_operator was only set on the first condition, leaving
    # conditions 2 and 3 unjoined. query_operator must be set on every condition except the last.
    import json

    route = respx.post("http://chatwoot.test/api/v1/accounts/1/conversations/filter").mock(
        return_value=Response(200, json={"payload": [], "meta": {"all_count": 1}})
    )

    await mcp.call_tool(
        "get_category_statistics",
        {"since": "2026-08-01", "until": "2026-08-10", "categories": ["Bug"]},
    )

    sent = json.loads(route.calls.last.request.content)["payload"]
    assert len(sent) == 3
    assert all("query_operator" in c for c in sent[:-1])
    assert "query_operator" not in sent[-1]
