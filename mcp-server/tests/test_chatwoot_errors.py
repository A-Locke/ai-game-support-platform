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
