from app import cli, mcp_client
from app.models import ClassificationResult
from app.workflows import classify as classify_module


class FakeMCP:
    """Records every call_tool invocation; get_conversation_messages responses are keyed by
    conversation_id so tests can give different conversations different message histories."""

    def __init__(self, messages_by_conversation: dict[int, list[dict]], responses: dict | None = None):
        self.calls: list[tuple[str, dict]] = []
        self._messages_by_conversation = messages_by_conversation
        self._responses = responses or {}

    async def call_tool(self, name: str, **arguments) -> dict:
        self.calls.append((name, arguments))
        if name == "get_conversation_messages":
            return {"payload": self._messages_by_conversation[arguments["conversation_id"]]}
        if name in self._responses:
            return self._responses[name]
        return {}

    def calls_named(self, name: str) -> list[dict]:
        return [args for called, args in self.calls if called == name]


def _incoming(message_id: int, content: str = "hello") -> dict:
    return {"id": message_id, "message_type": 0, "private": False, "content": content}


def _private_note(message_id: int, content: str = "AI note") -> dict:
    return {"id": message_id, "message_type": 1, "private": True, "content": content}


async def _async_return(value):
    return value


async def test_process_one_calls_the_shared_workflow_function(monkeypatch):
    captured = {}

    async def _fake_process(conversation_id, message_id):
        captured["args"] = (conversation_id, message_id)
        return {"status": "processed"}

    monkeypatch.setattr(cli, "process_incoming_message", _fake_process)

    result = await cli.process_one(42, 100)

    assert captured["args"] == (42, 100)
    assert result == {"status": "processed"}


async def test_process_unprocessed_uses_latest_incoming_message_not_last_message_overall(monkeypatch):
    # Regression test: found live -- a conversation's overall last message is often this
    # workflow's own private note (message_type outgoing/private), not a customer message.
    # Using it as the idempotency target created an infinite reprocessing loop. The id passed
    # to process_incoming_message must be the latest *incoming* message only.
    fake = FakeMCP(
        messages_by_conversation={
            1: [_incoming(10), _private_note(11), _private_note(12)],  # notes came after the message
        },
        responses={"search_conversations": {"payload": [{"id": 1}]}},
    )
    monkeypatch.setattr(mcp_client, "call_tool", fake.call_tool)

    captured = {}

    async def _fake_process(conversation_id, message_id):
        captured["args"] = (conversation_id, message_id)
        return {"status": "processed"}

    monkeypatch.setattr(cli, "process_incoming_message", _fake_process)

    await cli.process_unprocessed()

    assert captured["args"] == (1, 10)  # the incoming message, not note id 12


async def test_process_unprocessed_sweeps_multiple_conversations(monkeypatch):
    fake = FakeMCP(
        messages_by_conversation={
            1: [_incoming(10)],
            2: [_incoming(20), _incoming(21)],
        },
        responses={"search_conversations": {"payload": [{"id": 1}, {"id": 2}]}},
    )
    monkeypatch.setattr(mcp_client, "call_tool", fake.call_tool)

    processed = []

    async def _fake_process(conversation_id, message_id):
        processed.append((conversation_id, message_id))
        return {"status": "processed"}

    monkeypatch.setattr(cli, "process_incoming_message", _fake_process)

    results = await cli.process_unprocessed()

    assert processed == [(1, 10), (2, 21)]  # conversation 2's latest incoming message is 21
    assert len(results) == 2


async def test_process_unprocessed_relies_on_workflows_own_idempotency_check(monkeypatch):
    # cli.py deliberately does not duplicate the "is this stale" comparison -- it always calls
    # process_incoming_message and trusts its own idempotency check (docs/adr/0003, D3). This
    # uses the real classify_module.process_incoming_message to prove an already-processed
    # conversation is correctly skipped end-to-end, and stays skipped on a second sweep (the
    # actual bug found live -- see the "latest incoming message" test above).
    fake = FakeMCP(
        messages_by_conversation={1: [_incoming(10), _private_note(11)]},
        responses={
            "search_conversations": {"payload": [{"id": 1}]},
            "get_conversation": {"id": 1, "custom_attributes": {"ai_last_processed_message_id": "10"}},
        },
    )
    monkeypatch.setattr(mcp_client, "call_tool", fake.call_tool)
    monkeypatch.setattr(cli, "process_incoming_message", classify_module.process_incoming_message)

    called = False

    def _spy(messages):
        nonlocal called
        called = True
        return _async_return(
            ClassificationResult(category="Bug", spam=False, requires_human=False, confidence=0.5, reason="x")
        )

    monkeypatch.setattr(classify_module, "classify_conversation", _spy)

    results = await cli.process_unprocessed()

    assert results[0]["status"] == "skipped"
    assert called is False


async def test_process_unprocessed_skips_conversations_with_no_incoming_messages(monkeypatch):
    fake = FakeMCP(
        messages_by_conversation={1: [_private_note(11)]},  # only an internal note, no customer message
        responses={"search_conversations": {"payload": [{"id": 1}]}},
    )
    monkeypatch.setattr(mcp_client, "call_tool", fake.call_tool)

    called = False

    async def _fake_process(conversation_id, message_id):
        nonlocal called
        called = True

    monkeypatch.setattr(cli, "process_incoming_message", _fake_process)

    results = await cli.process_unprocessed()

    assert results == []
    assert called is False
