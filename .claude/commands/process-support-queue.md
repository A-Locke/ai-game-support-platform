Run the spam / categorisation / escalation / draft-response workflow against `support-mcp-server`
directly -- the MCP-only mode described in docs/adr/0003. This reproduces exactly what
`ai-service`'s automated pipeline does (`ai-service/app/workflows/classify.py` +
`claude_client.py`), except you (Claude, in this session) are the classifier instead of an
Anthropic API call, and you drive it by calling the MCP tools yourself.

Requires `support-mcp-server` connected as an MCP tool source for this session (see
docs/mcp-server.md and `.mcp.json`). This is a manually-maintained mirror of the Python
implementation, not generated from it -- see docs/adr/0003, D6. If `SUPPORT_CATEGORIES` in `.env`
has been changed from its default, use that list instead of the one below.

## Scope

Parse $ARGUMENTS:
- A specific conversation ID → process only that one, unconditionally (skip the idempotency
  check below).
- Blank → sweep every `open` conversation via `search_conversations(status="open")`.

## For each conversation in scope

1. **Fetch it.** Call `get_conversation(conversation_id)`.
2. **Check idempotency** (skip this step if a specific conversation ID was requested). Compare
   `custom_attributes.ai_last_processed_message_id` against
   `last_non_activity_message.id`. If they match, this conversation is already processed --
   skip it and move on.
3. **Fetch messages.** Call `get_conversation_messages(conversation_id)`. Keep only messages
   where `message_type` is `0` or `"incoming"` AND `private` is `false` -- these are the actual
   customer messages, not agent replies or prior AI notes. If there are none, skip this
   conversation.
4. **Ground yourself.** Read `knowledge-base/known-issues/*.md` and `knowledge-base/faq/*.md` in
   this repo for relevant known issues or FAQ answers before classifying -- don't guess at
   product behavior that's actually documented there.
5. **Classify.** Decide:
   - `category` — one of: `Bug`, `Crash`, `Technical`, `Installation`, `Account`, `Performance`,
     `Billing`, `Feature Request`, `Feedback`, `Other`, `Spam` (case as written here; the tag
     applied to Chatwoot is lowercase).
   - `spam` — true/false. Obvious promotional/scam content with no genuine support request.
   - `requires_human` — true/false. True whenever a human should look at this before anything
     player-facing happens -- err toward true, not false, for anything ambiguous.
   - `confidence` — 0.0-1.0.
   - `reason` — one or two sentences a support agent can read at a glance.
   - `draft_response` — only if `requires_human` is true AND you can ground a reply in a real
     known issue or FAQ entry from step 4. Otherwise omit it. Never invent a workaround, a
     timeline, or a policy that isn't actually documented.
6. **Apply the result**, in this order:
   - If `spam`: `add_conversation_tag(["spam"])`,
     `set_conversation_attributes({"ai_category": "Spam", "ai_confidence": <confidence>})`,
     `update_conversation_status("pending")`.
   - Else: `add_conversation_tag([<category, lowercase>])`,
     `set_conversation_attributes({"ai_category": <category>, "ai_confidence": <confidence>})`.
   - Always: `create_internal_note` with content
     `"AI classification: <category> (confidence <confidence>). <reason>"`.
   - If `requires_human`: `add_conversation_tag(["human-escalated"])`.
   - If a `draft_response` was produced: `create_draft_response(<draft_response>)`.
   - Finally: `set_conversation_attributes({"ai_last_processed_message_id": "<latest message id>"})`
     to mark it processed.

## Hard rules

- **Never** send anything to the customer directly. There is no tool in `support-mcp-server`
  that does this -- `create_draft_response` and `create_internal_note` both write private,
  agent-only Chatwoot messages. If you find yourself wanting to reply to the customer directly,
  stop -- that's out of scope for this command.
- Don't fabricate a known-issue match, a policy, or a workaround that isn't actually present in
  `knowledge-base/`. If nothing relevant exists, say so in `reason` and leave `draft_response`
  unset.

## When done

Summarize what happened as a table: conversation ID, category, spam?, escalated?, draft created?
one row per conversation actually processed (not skipped ones, unless none were processed at
all).
