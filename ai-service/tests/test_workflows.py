import pytest

from app import mcp_client
from app.mcp_client import MCPToolError
from app.models import ClassificationResult
from app.workflows import classify as classify_module


class FakeMCP:
    """Records every call_tool invocation and returns canned responses per tool name."""

    def __init__(self, responses: dict | None = None):
        self.calls: list[tuple[str, dict]] = []
        self._responses = responses or {}
        self._conversation_attributes: dict = {}

    async def call_tool(self, name: str, **arguments) -> dict:
        self.calls.append((name, arguments))
        if name == "get_conversation":
            return {"id": arguments["conversation_id"], "custom_attributes": self._conversation_attributes}
        if name in self._responses:
            return self._responses[name]
        return {}

    def calls_named(self, name: str) -> list[dict]:
        return [args for called, args in self.calls if called == name]


def _player_messages_payload(*texts: str) -> dict:
    return {"payload": [{"message_type": "incoming", "private": False, "content": t} for t in texts]}


@pytest.fixture
def spam_result() -> ClassificationResult:
    return ClassificationResult(
        category="Spam", spam=True, requires_human=False, confidence=0.97, reason="Obvious spam link."
    )


@pytest.fixture
def bug_result() -> ClassificationResult:
    return ClassificationResult(
        category="Bug", spam=False, requires_human=False, confidence=0.8, reason="Minor visual glitch."
    )


@pytest.fixture
def escalation_result() -> ClassificationResult:
    return ClassificationResult(
        category="Crash",
        spam=False,
        requires_human=True,
        confidence=0.94,
        reason="Repeatable crash, matches known issue KI-014.",
        draft_response="Thanks for the report! This is a known issue (KI-014)...",
    )


async def test_spam_conversation_is_tagged_and_moved_to_pending(monkeypatch, spam_result):
    fake = FakeMCP({"get_conversation_messages": _player_messages_payload("buy cheap gold now!!!")})
    monkeypatch.setattr(mcp_client, "call_tool", fake.call_tool)
    monkeypatch.setattr(classify_module, "classify_conversation", lambda messages: _async_return(spam_result))

    result = await classify_module.process_incoming_message(conversation_id=1, message_id=100)

    assert result["status"] == "processed"
    assert result["spam"] is True
    tag_calls = fake.calls_named("add_conversation_tag")
    assert {"conversation_id": 1, "tags": ["spam"]} in tag_calls
    status_calls = fake.calls_named("update_conversation_status")
    assert {"conversation_id": 1, "status": "pending"} in status_calls
    # Spam is never deleted -- no delete-shaped tool exists to call in the first place.


async def test_bug_conversation_is_categorized(monkeypatch, bug_result):
    fake = FakeMCP({"get_conversation_messages": _player_messages_payload("small texture glitch on the map")})
    monkeypatch.setattr(mcp_client, "call_tool", fake.call_tool)
    monkeypatch.setattr(classify_module, "classify_conversation", lambda messages: _async_return(bug_result))

    result = await classify_module.process_incoming_message(conversation_id=2, message_id=200)

    assert result["category"] == "Bug"
    tag_calls = fake.calls_named("add_conversation_tag")
    assert {"conversation_id": 2, "tags": ["bug"]} in tag_calls
    attr_calls = fake.calls_named("set_conversation_attributes")
    assert any(c["attributes"].get("ai_category") == "Bug" for c in attr_calls)


async def test_escalation_creates_note_and_draft_never_auto_sent(monkeypatch, escalation_result):
    fake = FakeMCP({"get_conversation_messages": _player_messages_payload("crashes every time in the Cathedral")})
    monkeypatch.setattr(mcp_client, "call_tool", fake.call_tool)
    monkeypatch.setattr(classify_module, "classify_conversation", lambda messages: _async_return(escalation_result))

    result = await classify_module.process_incoming_message(conversation_id=3, message_id=300)

    assert result["requires_human"] is True
    assert fake.calls_named("create_internal_note")
    assert {"conversation_id": 3, "tags": ["human-escalated"]} in fake.calls_named("add_conversation_tag")
    draft_calls = fake.calls_named("create_draft_response")
    assert draft_calls and draft_calls[0]["content"] == escalation_result.draft_response
    # No tool in this project's MCP surface sends a player-facing message -- draft storage
    # is a private note (see mcp-server's create_draft_response), which is the whole point.


async def test_idempotent_duplicate_event_is_skipped(monkeypatch, bug_result):
    fake = FakeMCP({"get_conversation_messages": _player_messages_payload("hello")})
    fake._conversation_attributes = {"ai_last_processed_message_id": "400"}
    monkeypatch.setattr(mcp_client, "call_tool", fake.call_tool)
    was_called = False

    def _spy(messages):
        nonlocal was_called
        was_called = True
        return _async_return(bug_result)

    monkeypatch.setattr(classify_module, "classify_conversation", _spy)

    result = await classify_module.process_incoming_message(conversation_id=4, message_id=400)

    assert result["status"] == "skipped"
    assert was_called is False


async def test_mcp_unreachable_returns_error_status(monkeypatch):
    async def _raise(name, **kwargs):
        raise MCPToolError("connection refused")

    monkeypatch.setattr(mcp_client, "call_tool", _raise)

    result = await classify_module.process_incoming_message(conversation_id=5, message_id=500)

    assert result["status"] == "error"


async def _async_return(value):
    return value
