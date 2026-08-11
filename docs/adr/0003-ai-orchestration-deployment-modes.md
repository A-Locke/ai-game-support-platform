# ADR 0003: AI Orchestration Deployment Modes

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-11 |
| **Related** | [ai-workflows.md](../ai-workflows.md) · [ADR 0001](0001-architecture-and-tech-stack.md) |

## Context

Until now, `ai-service` (a FastAPI webhook server calling the Anthropic API directly) was the
only supported way to run the classification workflow. During live testing (PROJECT_JOURNAL.md,
Milestone 2), the project owner drove the exact same `mcp-server` tools directly from a connected
Claude Code session instead — no `ai-service`, no `ANTHROPIC_API_KEY` anywhere, real
content-aware classification performed by Claude itself acting as the orchestrator. That worked
because `mcp-server` already treats every MCP client identically (ADR 0001's whole point) — it
has no idea whether it's talking to `ai-service`'s Python client or a human's Claude Code
session. The project owner asked for this to become a first-class, supported mode: a CLI for
on-demand/batch use of `ai-service`'s own logic without a persistent server, and a way to run the
whole project *without* `ai-service` at all when a human or a scheduled Claude routine is doing
the classification via the MCP connector directly.

## Decision Drivers

1. **No duplicated business logic.** Classification/spam/categorize/escalate rules must have
   exactly one real implementation, reused by every entry point that uses `ai-service`'s own code.
2. **Exploit, don't replace, ADR 0001's client-agnostic MCP server** — this feature should be a
   consequence of that design, not a new mechanism bolted alongside it.
3. **`docker compose up -d` should keep working** for anyone already following the documented
   quickstart, even though its meaning changes (see D4).
4. **The MCP-only mode must be genuinely self-sufficient** — no `ai-service`, no Anthropic API
   key running anywhere, exactly as proven live in Milestone 2.

## Decisions

### D1: A CLI entry point reuses the exact same workflow function the webhook handler calls

**Decision:** `ai-service/app/cli.py` calls `app.workflows.classify.process_incoming_message` —
the identical function `app/main.py`'s webhook handler calls. No parallel classification logic.

**Why:** Two implementations of "how do we classify a ticket" is exactly the kind of duplication
ADR 0001 already avoids for the Chatwoot access layer (every write goes through one
`mcp_client.call_tool`). The transport — HTTP webhook vs. CLI invocation — is the only thing that
differs; the decision logic underneath must not fork.

### D2: `process` for one conversation, `process-unprocessed` for a batch sweep

**Decision:** `python -m app.cli process <conversation_id> <message_id>` handles a single
conversation. `python -m app.cli process-unprocessed` searches open conversations and processes
every one whose `ai_last_processed_message_id` doesn't match its latest message.

**Why:** Matches the two real use cases: reprocessing a specific ticket (e.g. after fixing a
bug), and catching up an entire queue — useful if `ai-service` runs periodically instead of as a
live webhook receiver, or was down for a while and missed events.

### D3: Batch discovery reuses the existing idempotency attribute, not a new queue concept

**Decision:** `process-unprocessed` treats a conversation as needing work exactly when its
`ai_last_processed_message_id` custom attribute doesn't match its latest message id — the same
check `process_incoming_message` already performs internally on every call (ADR 0001, D5).

**Why:** No new state to invent, maintain, or let drift out of sync with the webhook path's own
notion of "already handled."

### D4: `ai-service` moves behind a Compose profile; the bare `docker compose up -d` default changes

**Decision:** `docker-compose.yml` gives the `ai-service` service `profiles: ["automated"]`.
`docker compose up -d` (no profile) now starts everything *except* `ai-service`. Reproducing the
previous default requires `docker compose --profile automated up -d`.

**Why:** This is the one place in the project a Compose profile is the right tool — contrast
[ADR 0002, D8](0002-postgres-backup-and-recovery.md#d8-backups-are-opt-in-via-configuration-not-via-a-compose-profile),
where backups stay always-on-but-inert because *whether S3 is configured yet* isn't a meaningful
mode choice. Here, *which orchestration mode a user is in* — automated `ai-service`, or
MCP-only/Claude-routine — genuinely is the choice being made, and flipping the plain-command
default to the one that needs no Anthropic API key at all matches "a way to run the project
without ai-service" being a real, first-class mode rather than an afterthought.

**Consequences:** This is a deliberate, called-out behavior change from what Milestones 1–2's
docs described. `docs/setup.md` and the README are updated to match; anyone following older
instructions verbatim would get a stack with no `ai-service` running and needs to notice the
`--profile automated` flag. `mcp-server` carries no profile (always starts), since MCP-only mode
still needs it.

### D5: The Claude-routine playbook is a committed, versioned artifact, not verbal instructions

**Decision:** `.claude/commands/process-support-queue.md` documents the classify/tag/escalate/draft
procedure as a Claude Code slash command, callable manually or wired into a scheduled Claude
routine.

**Why:** Milestone 2 already proved a human-driven session doing this by hand works. Turning that
into a committed, repeatable command means anyone — a scheduled routine, a different session, a
teammate — can reproduce the same behavior without reading `claude_client.py` first. It's the
natural single-source-of-truth artifact for "how do we do this without `ai-service`," the same
way `claude_client.py` is the source of truth for "how do we do this with `ai-service`."

### D6: The playbook is a manually-maintained parallel implementation, not generated from Python

**Decision:** The command's prompt/schema description is written to closely mirror
`claude_client.py`'s actual category list, tag names, and idempotency attribute, but there is no
automated mechanism keeping them in sync.

**Why:** No tooling in this project generates one from the other, and pretending otherwise would
be dishonest. Stated plainly as a known limitation: if `SUPPORT_CATEGORIES` changes, both
`ai-service`'s config and the command file need updating by hand.

## Consequences (Overall)

**Positive:** Three ways to run the exact same classification logic (webhook-driven `ai-service`,
CLI-driven `ai-service`, or a Claude Code routine via MCP) with zero duplicated business rules
between the first two, and the third genuinely usable with no `ai-service` or Anthropic API key
deployed at all.

**Negative / accepted trade-offs:** The default `docker compose up -d` behavior changes from what
earlier milestones documented — a real, if well-flagged, breaking change to the quickstart. The
Claude-routine playbook can drift out of sync with `ai-service`'s Python implementation over time
since nothing enforces they match.
