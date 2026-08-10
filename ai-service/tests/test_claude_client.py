import respx
from httpx import Response

from app.claude_client import classify_conversation, summarize_report
from app.config import settings
from tests.conftest import ANTHROPIC_MESSAGES_URL, text_response, tool_use_response


async def test_missing_api_key_falls_back_instead_of_crashing():
    # Regression test: found live against a real deployment with no ANTHROPIC_API_KEY set.
    # The anthropic SDK raises a plain TypeError from request *construction* (before any HTTP
    # call) when the key is empty, which `except APIError` did not catch -- it 500'd the whole
    # webhook handler instead of degrading to the safe fallback. No respx mock here on purpose:
    # a real network call would mean the TypeError wasn't actually raised pre-flight.
    original_key = settings.anthropic_api_key
    settings.anthropic_api_key = ""
    try:
        result = await classify_conversation(["some message"])
    finally:
        settings.anthropic_api_key = original_key

    assert result.category == "Other"
    assert result.requires_human is True


@respx.mock
async def test_valid_classification_returns_parsed_result():
    respx.post(ANTHROPIC_MESSAGES_URL).mock(
        return_value=Response(
            200,
            json=tool_use_response(
                {
                    "category": "Crash",
                    "spam": False,
                    "requires_human": True,
                    "confidence": 0.94,
                    "reason": "Repeatable crash entering the Cathedral after the third relic.",
                    "draft_response": "Thanks for the report!",
                }
            ),
        )
    )

    result = await classify_conversation(["The game crashes every time I enter the Cathedral"])

    assert result.category == "Crash"
    assert result.requires_human is True
    assert result.confidence == 0.94
    assert result.draft_response == "Thanks for the report!"


@respx.mock
async def test_malformed_output_falls_back_to_safe_default():
    # Missing the required "confidence" field.
    respx.post(ANTHROPIC_MESSAGES_URL).mock(
        return_value=Response(
            200,
            json=tool_use_response(
                {
                    "category": "Bug",
                    "spam": False,
                    "requires_human": False,
                    "reason": "incomplete payload",
                }
            ),
        )
    )

    result = await classify_conversation(["some message"])

    assert result.category == "Other"
    assert result.requires_human is True


@respx.mock
async def test_no_tool_use_block_falls_back():
    respx.post(ANTHROPIC_MESSAGES_URL).mock(return_value=Response(200, json=text_response("I'm not sure.")))

    result = await classify_conversation(["some message"])

    assert result.category == "Other"
    assert result.requires_human is True


@respx.mock
async def test_claude_api_failure_falls_back_after_retry():
    route = respx.post(ANTHROPIC_MESSAGES_URL).mock(return_value=Response(529, json={"error": "overloaded"}))

    result = await classify_conversation(["some message"])

    assert result.category == "Other"
    assert result.requires_human is True
    assert route.call_count == 2  # one retry, per claude_client's retry-once policy


@respx.mock
async def test_summarize_report_returns_text():
    respx.post(ANTHROPIC_MESSAGES_URL).mock(return_value=Response(200, json=text_response("Mostly bug reports this week.")))

    summary = await summarize_report({"total_conversations": 10})

    assert summary == "Mostly bug reports this week."


@respx.mock
async def test_summarize_report_handles_api_failure():
    respx.post(ANTHROPIC_MESSAGES_URL).mock(return_value=Response(500, json={"error": "server error"}))

    summary = await summarize_report({"total_conversations": 10})

    assert "unavailable" in summary.lower()
