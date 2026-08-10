#!/usr/bin/env python3
"""One-time (idempotent) Chatwoot configuration: registers ai-service's webhook, creates the
labels the AI workflows use, and creates the custom attributes they read/write. Run after
docs/setup.md step 3 (first admin + API access token created).

Requires on the host: CHATWOOT_ACCOUNT_ID, CHATWOOT_API_ACCESS_TOKEN, AI_WEBHOOK_SHARED_SECRET
(same values as .env). Talks to Chatwoot's public URL (localhost:3000 for local dev), not the
Docker-internal one -- this script runs on the host, not inside a container.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

CHATWOOT_URL = os.environ.get("CHATWOOT_PUBLIC_URL", "http://localhost:3000")
ACCOUNT_ID = os.environ.get("CHATWOOT_ACCOUNT_ID", "1")
API_TOKEN = os.environ.get("CHATWOOT_API_ACCESS_TOKEN", "")
WEBHOOK_SECRET = os.environ.get("AI_WEBHOOK_SHARED_SECRET", "")
AI_SERVICE_WEBHOOK_URL = os.environ.get(
    "AI_SERVICE_WEBHOOK_URL", "http://ai-service:8000/webhooks/chatwoot"
)
CATEGORIES = [
    c.strip()
    for c in os.environ.get(
        "SUPPORT_CATEGORIES",
        "Bug,Crash,Gameplay,Technical,Installation,Account,Performance,Billing,Feedback,Other",
    ).split(",")
    if c.strip()
]

LABELS = ["spam", "human-escalated", "ai-draft"] + [c.lower() for c in CATEGORIES]

CUSTOM_ATTRIBUTES = [
    {"attribute_display_name": "AI Category", "attribute_key": "ai_category", "attribute_display_type": "text"},
    {
        "attribute_display_name": "AI Confidence",
        "attribute_key": "ai_confidence",
        "attribute_display_type": "number",
    },
    {
        "attribute_display_name": "AI Last Processed Message Id",
        "attribute_key": "ai_last_processed_message_id",
        "attribute_display_type": "text",
    },
]


def _client() -> httpx.Client:
    if not API_TOKEN:
        print("CHATWOOT_API_ACCESS_TOKEN is not set -- see docs/setup.md step 3.", file=sys.stderr)
        sys.exit(1)
    return httpx.Client(base_url=CHATWOOT_URL, headers={"api_access_token": API_TOKEN}, timeout=15.0)


def ensure_labels(client: httpx.Client) -> None:
    existing = {label["title"] for label in client.get(f"/api/v1/accounts/{ACCOUNT_ID}/labels").json().get("payload", [])}
    for name in LABELS:
        if name in existing:
            print(f"label '{name}' already exists")
            continue
        response = client.post(f"/api/v1/accounts/{ACCOUNT_ID}/labels", json={"title": name, "show_on_sidebar": True})
        response.raise_for_status()
        print(f"created label '{name}'")


def ensure_custom_attributes(client: httpx.Client) -> None:
    existing = {
        a["attribute_key"] for a in client.get(f"/api/v1/accounts/{ACCOUNT_ID}/custom_attribute_definitions").json()
    }
    for attribute in CUSTOM_ATTRIBUTES:
        if attribute["attribute_key"] in existing:
            print(f"custom attribute '{attribute['attribute_key']}' already exists")
            continue
        response = client.post(
            f"/api/v1/accounts/{ACCOUNT_ID}/custom_attribute_definitions",
            json={**attribute, "attribute_model": "conversation_attribute"},
        )
        response.raise_for_status()
        print(f"created custom attribute '{attribute['attribute_key']}'")


def ensure_webhook(client: httpx.Client) -> None:
    url = AI_SERVICE_WEBHOOK_URL
    if WEBHOOK_SECRET:
        url = f"{url}?secret={WEBHOOK_SECRET}"

    existing = client.get(f"/api/v1/accounts/{ACCOUNT_ID}/webhooks").json().get("payload", [])
    for webhook in existing:
        if webhook["url"].split("?")[0] == AI_SERVICE_WEBHOOK_URL:
            print("webhook already registered")
            return

    response = client.post(
        f"/api/v1/accounts/{ACCOUNT_ID}/webhooks",
        json={"webhook": {"url": url, "subscriptions": ["message_created"]}},
    )
    response.raise_for_status()
    print(f"registered webhook for message_created -> {AI_SERVICE_WEBHOOK_URL}")


def main() -> None:
    with _client() as client:
        ensure_labels(client)
        ensure_custom_attributes(client)
        ensure_webhook(client)
    print("done.")


if __name__ == "__main__":
    main()
