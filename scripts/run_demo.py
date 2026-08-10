#!/usr/bin/env python3
"""Seeds the three demo scenarios from game-data/sample-tickets/ against a running local
Chatwoot + ai-service, then polls each conversation until ai-service has processed it and
prints the result. Finishes with the reporting scenario. See docs/setup.md step 5 and the
top-level README's "Demo scenarios" section.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

CHATWOOT_URL = os.environ.get("CHATWOOT_PUBLIC_URL", "http://localhost:3000")
AI_SERVICE_URL = os.environ.get("AI_SERVICE_PUBLIC_URL", "http://localhost:8000")
ACCOUNT_ID = os.environ.get("CHATWOOT_ACCOUNT_ID", "1")
API_TOKEN = os.environ.get("CHATWOOT_API_ACCESS_TOKEN", "")

TICKETS_DIR = Path(__file__).resolve().parent.parent / "game-data" / "sample-tickets"
POLL_TIMEOUT_SECONDS = 30
POLL_INTERVAL_SECONDS = 2


def _client() -> httpx.Client:
    if not API_TOKEN:
        print("CHATWOOT_API_ACCESS_TOKEN is not set -- see docs/setup.md step 3.", file=sys.stderr)
        sys.exit(1)
    return httpx.Client(base_url=CHATWOOT_URL, headers={"api_access_token": API_TOKEN}, timeout=15.0)


def _first_inbox_id(client: httpx.Client) -> int:
    inboxes = client.get(f"/api/v1/accounts/{ACCOUNT_ID}/inboxes").json().get("payload", [])
    if not inboxes:
        print("No inbox found -- complete the Chatwoot onboarding wizard first (docs/setup.md step 3).", file=sys.stderr)
        sys.exit(1)
    return inboxes[0]["id"]


def _create_conversation(client: httpx.Client, inbox_id: int, ticket: dict) -> int:
    contact_response = client.post(
        f"/api/v1/accounts/{ACCOUNT_ID}/contacts",
        json={"name": ticket["contact"]["name"], "email": ticket["contact"]["email"], "inbox_id": inbox_id},
    )
    contact_response.raise_for_status()
    contact_id = contact_response.json()["payload"]["contact"]["id"]

    conversation_response = client.post(
        f"/api/v1/accounts/{ACCOUNT_ID}/conversations",
        json={
            "source_id": f"demo-{ticket['scenario']}-{uuid.uuid4()}",
            "inbox_id": inbox_id,
            "contact_id": contact_id,
            "status": "open",
            "message": {"content": ticket["message"]},
        },
    )
    conversation_response.raise_for_status()
    return conversation_response.json()["id"]


def _poll_for_result(client: httpx.Client, conversation_id: int) -> dict:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        conversation = client.get(f"/api/v1/accounts/{ACCOUNT_ID}/conversations/{conversation_id}").json()
        if conversation.get("custom_attributes", {}).get("ai_last_processed_message_id"):
            return conversation
        time.sleep(POLL_INTERVAL_SECONDS)
    print(f"  (timed out waiting for ai-service to process conversation {conversation_id})")
    return conversation


def run_scenarios(client: httpx.Client) -> None:
    inbox_id = _first_inbox_id(client)
    for ticket_path in sorted(TICKETS_DIR.glob("*.json")):
        ticket = json.loads(ticket_path.read_text(encoding="utf-8"))
        print(f"\n=== Scenario: {ticket['scenario']} ===")
        print(f"Player message: {ticket['message'][:100]}...")

        conversation_id = _create_conversation(client, inbox_id, ticket)
        print(f"Created conversation {conversation_id}, waiting for ai-service...")

        conversation = _poll_for_result(client, conversation_id)
        attrs = conversation.get("custom_attributes", {})
        labels_response = client.get(f"/api/v1/accounts/{ACCOUNT_ID}/conversations/{conversation_id}/labels")
        labels = labels_response.json().get("payload", [])

        print(f"  category:        {attrs.get('ai_category')}")
        print(f"  confidence:      {attrs.get('ai_confidence')}")
        print(f"  labels:          {labels}")
        print(f"  status:          {conversation.get('status')}")


def run_reporting_scenario() -> None:
    print("\n=== Scenario: reporting ===")
    print('Question: "What are the main support issues reported by players this week?"')
    response = httpx.get(f"{AI_SERVICE_URL}/reports/summary", timeout=30.0)
    response.raise_for_status()
    body = response.json()
    print("\nRaw data:", json.dumps(body["data"], indent=2))
    print("\nAI summary:\n", body["summary"])


def main() -> None:
    with _client() as client:
        run_scenarios(client)
    run_reporting_scenario()


if __name__ == "__main__":
    main()
