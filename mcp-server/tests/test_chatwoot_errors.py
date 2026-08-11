import httpx
import pytest
import respx
from httpx import Response

from app.chatwoot_client import ChatwootAPIError, ChatwootClient


@pytest.fixture
def client():
    return ChatwootClient(base_url="http://chatwoot.test", account_id=1, api_access_token="tok")


@respx.mock
async def test_http_error_status_raises_chatwoot_api_error(client):
    respx.get("http://chatwoot.test/api/v1/accounts/1/conversations/1").mock(
        return_value=Response(404, text="not found")
    )

    with pytest.raises(ChatwootAPIError) as exc_info:
        await client.get_conversation(1)

    assert exc_info.value.status_code == 404


@respx.mock
async def test_network_failure_raises_chatwoot_api_error(client):
    respx.get("http://chatwoot.test/api/v1/accounts/1/conversations/1").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with pytest.raises(ChatwootAPIError) as exc_info:
        await client.get_conversation(1)

    assert exc_info.value.status_code == 0


@respx.mock
async def test_no_content_response_returns_empty_dict(client):
    respx.post("http://chatwoot.test/api/v1/accounts/1/conversations/1/toggle_status").mock(
        return_value=Response(204)
    )

    result = await client.update_conversation_status(1, "resolved")

    assert result == {}


@respx.mock
async def test_api_access_token_header_is_sent(client):
    route = respx.get("http://chatwoot.test/api/v1/accounts/1/conversations/1").mock(
        return_value=Response(200, json={"id": 1})
    )

    await client.get_conversation(1)

    assert route.calls.last.request.headers["api_access_token"] == "tok"


@respx.mock
async def test_search_conversations_unwraps_the_data_key_for_the_no_query_path(client):
    # Regression test: found live -- GET /conversations (status-only, no query) nests its
    # response under "data", unlike GET /conversations/search (query given), which returns the
    # same {"meta", "payload"} shape at the top level. A CLI batch sweep silently saw "no open
    # conversations" against a database that had six, because it only checked for a top-level
    # "payload" key. Both code paths must return the identical shape to callers.
    respx.get("http://chatwoot.test/api/v1/accounts/1/conversations").mock(
        return_value=Response(200, json={"data": {"meta": {"all_count": 6}, "payload": [{"id": 1}]}})
    )

    result = await client.search_conversations(status="open")

    assert result == {"meta": {"all_count": 6}, "payload": [{"id": 1}]}


@respx.mock
async def test_search_conversations_query_path_already_flat(client):
    respx.get("http://chatwoot.test/api/v1/accounts/1/conversations/search").mock(
        return_value=Response(200, json={"meta": {"all_count": 1}, "payload": [{"id": 2}]})
    )

    result = await client.search_conversations(query="crash")

    assert result == {"meta": {"all_count": 1}, "payload": [{"id": 2}]}
