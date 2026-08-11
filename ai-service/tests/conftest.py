import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def configured_settings():
    settings.anthropic_api_key = "sk-test"
    settings.anthropic_model = "claude-sonnet-5"
    settings.mcp_server_url = "http://mcp-server.test/mcp"
    settings.mcp_auth_token = "test-mcp-token"
    settings.ai_webhook_shared_secret = "test-webhook-secret"
    settings.support_categories = "Bug,Crash,Technical,Installation,Account,Performance,Billing,Feature Request,Feedback,Other"
    settings.jira_mcp_url = ""
    settings.jira_mcp_api_token = ""
    settings.azure_devops_mcp_url = ""
    settings.azure_devops_mcp_pat = ""
    yield


ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


def tool_use_response(input_payload: dict, tool_name: str = "record_classification") -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "content": [{"type": "tool_use", "id": "toolu_test", "name": tool_name, "input": input_payload}],
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def text_response(text: str) -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
