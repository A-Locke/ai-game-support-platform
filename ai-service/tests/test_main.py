from starlette.testclient import TestClient

from app import main as main_module
from app.main import app

client = TestClient(app)


def _payload(**overrides) -> dict:
    base = {
        "event": "message_created",
        "id": 42,
        "content": "hello",
        "message_type": "incoming",
        "private": False,
        "conversation": {"id": 7},
    }
    base.update(overrides)
    return base


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_webhook_rejects_wrong_secret():
    response = client.post("/webhooks/chatwoot?secret=wrong", json=_payload())
    assert response.status_code == 401


def test_webhook_ignores_agent_reply(monkeypatch):
    called = False

    async def _spy(conversation_id, message_id):
        nonlocal called
        called = True
        return {"status": "processed"}

    monkeypatch.setattr(main_module, "process_incoming_message", _spy)

    response = client.post(
        "/webhooks/chatwoot?secret=test-webhook-secret", json=_payload(message_type="outgoing")
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert called is False


def test_webhook_ignores_private_note_to_avoid_self_trigger(monkeypatch):
    called = False

    async def _spy(conversation_id, message_id):
        nonlocal called
        called = True
        return {"status": "processed"}

    monkeypatch.setattr(main_module, "process_incoming_message", _spy)

    response = client.post("/webhooks/chatwoot?secret=test-webhook-secret", json=_payload(private=True))

    assert response.status_code == 200
    assert called is False


def test_webhook_dispatches_actionable_player_message(monkeypatch):
    received = {}

    async def _spy(conversation_id, message_id):
        received["conversation_id"] = conversation_id
        received["message_id"] = message_id
        return {"status": "processed", "category": "Bug", "spam": False, "requires_human": False}

    monkeypatch.setattr(main_module, "process_incoming_message", _spy)

    response = client.post("/webhooks/chatwoot?secret=test-webhook-secret", json=_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    assert received == {"conversation_id": 7, "message_id": 42}


def test_webhook_ignores_unrecognized_payload_without_error():
    response = client.post("/webhooks/chatwoot?secret=test-webhook-secret", json={"totally": "unexpected"})
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
