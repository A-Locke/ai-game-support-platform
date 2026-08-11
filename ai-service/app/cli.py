"""CLI entry point for on-demand/batch use of the same classification workflow the webhook
handler uses -- no persistent server, no separate business logic. See docs/adr/0003, D1-D3.

Usage:
    python -m app.cli process <conversation_id> <message_id>
    python -m app.cli process-unprocessed
"""

from __future__ import annotations

import argparse
import asyncio

from app import mcp_client
from app.workflows.classify import get_incoming_messages, process_incoming_message


async def process_one(conversation_id: int, message_id: int) -> dict:
    result = await process_incoming_message(conversation_id, message_id)
    print(f"conversation {conversation_id}: {result}")
    return result


async def process_unprocessed(status: str = "open") -> list[dict]:
    """Sweep conversations by status and process each one. process_incoming_message's own
    idempotency check (not duplicated here) decides whether a given conversation actually
    needs work -- see docs/adr/0003, D3.

    The "latest message" for idempotency purposes must be the latest genuine *incoming*
    (customer) message, not the conversation's last message overall -- found live: a
    conversation's last message is often this very workflow's own internal note or draft, so
    using it as the idempotency target created a message every sweep, which became the new
    "last message", which never matched the stored marker -- an infinite reprocessing loop on
    every run. See PROJECT_JOURNAL.md, Milestone 5.
    """
    payload = await mcp_client.call_tool("search_conversations", status=status)
    conversations = payload.get("payload", payload if isinstance(payload, list) else [])

    results = []
    for summary in conversations:
        conversation_id = summary.get("id")
        if conversation_id is None:
            continue

        incoming = await get_incoming_messages(conversation_id)
        message_ids = [m["id"] for m in incoming if m.get("id") is not None]
        if not message_ids:
            continue
        message_id = max(message_ids)

        result = await process_incoming_message(conversation_id, message_id)
        print(f"conversation {conversation_id}: {result}")
        results.append({"conversation_id": conversation_id, **result})

    if not results:
        print(f"no {status} conversations found")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run ai-service's classification workflow on demand, without the webhook server."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    process_parser = subparsers.add_parser("process", help="Process a single conversation")
    process_parser.add_argument("conversation_id", type=int)
    process_parser.add_argument("message_id", type=int)

    sweep_parser = subparsers.add_parser(
        "process-unprocessed", help="Sweep conversations by status and process any with a stale idempotency marker"
    )
    sweep_parser.add_argument("--status", default="open")

    args = parser.parse_args()

    if args.command == "process":
        asyncio.run(process_one(args.conversation_id, args.message_id))
    elif args.command == "process-unprocessed":
        asyncio.run(process_unprocessed(status=args.status))


if __name__ == "__main__":
    main()
