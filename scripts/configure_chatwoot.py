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
        "Bug,Crash,Technical,Installation,Account,Performance,Billing,Feature Request,Feedback,Other",
    ).split(",")
    if c.strip()
]

LABELS = ["spam", "human-escalated", "ai-draft"] + [c.lower() for c in CATEGORIES]

WIDGET_INBOX_NAME = "Website Live Chat"
WIDGET_WEBSITE_URL = os.environ.get("WIDGET_WEBSITE_URL", "http://localhost:8080")

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

    # GET .../webhooks nests the list one level deeper than every other list endpoint this script
    # reads ({"payload": {"webhooks": [...]}}, not {"payload": [...]}) -- found live, the naive
    # .get("payload", []) silently returned a dict, and iterating it yielded its one string key
    # ("webhooks") instead of webhook records, crashing on webhook["url"].
    existing = client.get(f"/api/v1/accounts/{ACCOUNT_ID}/webhooks").json().get("payload", {}).get("webhooks", [])
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


def ensure_website_widget_inbox(client: httpx.Client) -> dict | None:
    """Customer-facing live chat inbox (docs/adr/0009) -- separate from the API inbox the
    webhook/demo pipeline uses. Pre-chat form requires an email address, which is what makes the
    resolved-conversation notification below possible at all. Returns the inbox (existing or
    newly created), or None if inbox listing itself fails."""
    existing = client.get(f"/api/v1/accounts/{ACCOUNT_ID}/inboxes").json().get("payload", [])
    for inbox in existing:
        if inbox["name"] == WIDGET_INBOX_NAME:
            print(f"inbox '{WIDGET_INBOX_NAME}' already exists (id {inbox['id']})")
            return inbox

    response = client.post(
        f"/api/v1/accounts/{ACCOUNT_ID}/inboxes",
        json={
            "name": WIDGET_INBOX_NAME,
            "channel": {
                "type": "web_widget",
                "website_url": WIDGET_WEBSITE_URL,
                "welcome_title": "Hi there!",
                "welcome_tagline": "Ask us anything, we usually reply within a few hours.",
                "pre_chat_form_enabled": True,
                "pre_chat_form_options": {
                    "pre_chat_message": "Please share your email so we can follow up if you step away.",
                    # field_type/type are easy to get backwards -- field_type marks this as a
                    # Chatwoot "standard" field (vs. a contact/conversation custom attribute);
                    # type is fed straight into the widget's FormKit renderer as the actual input
                    # type, so it has to be a real one ("email", "text"), not "standard". Found
                    # live: getting this backwards doesn't error anywhere -- the API accepts and
                    # stores it fine -- it just silently renders as a generic message box with no
                    # email input, and a required-but-unrenderable field then blocks form submit
                    # entirely with no visible error. Confirmed against Chatwoot's own test
                    # fixture (app/javascript/widget/mixins/specs/configMixin.spec.js).
                    "pre_chat_fields": [
                        {
                            "field_type": "standard",
                            "name": "emailAddress",
                            "label": "Email",
                            "placeholder": "your@email.com",
                            "type": "email",
                            "required": True,
                            "enabled": True,
                        },
                        {
                            "field_type": "standard",
                            "name": "fullName",
                            "label": "Full name",
                            "placeholder": "Your name",
                            "type": "text",
                            "required": False,
                            "enabled": True,
                        },
                    ],
                },
            },
        },
    )
    response.raise_for_status()
    inbox = response.json()
    print(f"created inbox '{WIDGET_INBOX_NAME}' (id {inbox['id']}, website_token {inbox['website_token']})")
    return inbox


def ensure_resolved_notification_automation(client: httpx.Client, inbox_id: int) -> None:
    """Emails the conversation transcript to the customer when their ticket is marked resolved --
    docs/adr/0009, D2. The only way a customer finds out their issue was fixed without an
    account/login to check back with."""
    existing = client.get(f"/api/v1/accounts/{ACCOUNT_ID}/automation_rules").json().get("payload", [])
    for rule in existing:
        actions = rule.get("actions") or []
        if rule.get("event_name") == "conversation_resolved" and any(
            a.get("action_name") == "send_email_transcript" for a in actions
        ):
            print("resolved-conversation notification automation already exists")
            return

    response = client.post(
        f"/api/v1/accounts/{ACCOUNT_ID}/automation_rules",
        json={
            "name": "Notify customer when their conversation is resolved",
            "description": (
                "Emails the conversation transcript to the customer when their ticket is marked "
                "resolved, so they know it was addressed without needing an account or login."
            ),
            "event_name": "conversation_resolved",
            "conditions": [
                {"attribute_key": "inbox_id", "filter_operator": "equal_to", "values": [str(inbox_id)], "query_operator": None}
            ],
            "actions": [{"action_name": "send_email_transcript", "action_params": []}],
        },
    )
    response.raise_for_status()
    print("created resolved-conversation notification automation")


def main() -> None:
    with _client() as client:
        ensure_labels(client)
        ensure_custom_attributes(client)
        ensure_webhook(client)
        widget_inbox = ensure_website_widget_inbox(client)
        if widget_inbox:
            ensure_resolved_notification_automation(client, widget_inbox["id"])
    print("done.")


if __name__ == "__main__":
    main()
