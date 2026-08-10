# MCP Server

`mcp-server/` is a self-hosted [Model Context Protocol](https://modelcontextprotocol.io) server
that exposes a small, curated set of Chatwoot operations as MCP tools. See
[architecture.md](architecture.md) for how it fits into the overall system and
[ADR 0001](adr/0001-architecture-and-tech-stack.md) for why it's built the way it is.

## Why MCP here

The brief's core requirement is that the AI orchestration layer never talks to Chatwoot
directly — it only ever reaches Chatwoot through this server. That gives three concrete
benefits:

1. **A narrow, auditable surface.** ai-service (or any other MCP client) can only do what a
   tool explicitly allows — not "anything the Chatwoot API access token can do."
2. **Provider independence.** MCP is not Claude-specific. Any MCP-speaking client — a different
   LLM's agent framework, a CLI, a test harness — can call this server unmodified.
3. **A clean replacement seam.** If Chatwoot is ever swapped for another support platform, only
   this server's internals change; every client-facing tool name and shape stays the same.

Nothing in this server knows what an LLM is. It has no Claude SDK dependency and no concept of
"classification" or "spam" — see [D8 in ADR 0001](adr/0001-architecture-and-tech-stack.md#d8-mcp-tool-get_category_statistics-takes-categories-as-a-caller-supplied-argument).

## Tool reference

### Read-only

| Tool | Purpose |
|---|---|
| `get_conversation(conversation_id)` | Fetch a single conversation, including status and custom attributes. |
| `search_conversations(query?, status?, page?)` | Search or list conversations. |
| `get_conversation_messages(conversation_id)` | Full message history (player + agent + notes). |
| `search_contacts(query)` | Search players/contacts. |
| `get_support_statistics(since, until)` | Ticket volume, spam count, human-intervention count for a date range. Data retrieval only — no LLM involvement. |
| `get_category_statistics(since, until, categories)` | Per-category conversation counts. `categories` is supplied by the caller. |

### Mutating (gated by `MCP_ENABLE_MUTATIONS`)

| Tool | Purpose |
|---|---|
| `update_conversation_status(conversation_id, status)` | Change status: `open`, `resolved`, `pending`, `snoozed`. |
| `add_conversation_tag(conversation_id, tags)` | Attach labels (e.g. a category, or `spam`). |
| `set_conversation_attributes(conversation_id, attributes)` | Set custom attributes (e.g. `ai_category`, `ai_last_processed_message_id`). |
| `create_internal_note(conversation_id, content)` | Add a private, agent-only note. |
| `create_draft_response(conversation_id, content)` | Store a suggested reply as a private note tagged `ai-draft` — never sent to the player. |

Setting `MCP_ENABLE_MUTATIONS=false` disables the mutating group entirely (each call returns a
structured `{"error": true, ...}` result instead of touching Chatwoot), while every read-only
tool keeps working — useful for a read-only reporting deployment or a locked-down demo.

## Security model

- **Chatwoot credentials never reach the caller.** The Application API access token lives only
  in `mcp-server`'s environment; tool results are Chatwoot response bodies, not the token.
- **Read vs. mutating tools are separated** (brief §10) both by naming and by the
  `MCP_ENABLE_MUTATIONS` flag, so a deployment can be locked to reporting-only use.
- **All tool inputs are validated** by `fastmcp`'s schema generation from Python type hints
  before a tool body ever runs.
- **Chatwoot API failures never crash a tool** — they're caught and returned as a structured
  `{"error": true, "status_code": ..., "detail": ...}` payload, so a client (LLM or otherwise)
  gets something it can reason about instead of a stack trace.
- **Transport-level auth:** the stdio transport (local dev) has no auth — it's a trusted child
  process. The Streamable HTTP transport (used for any networked deployment) requires a bearer
  token (`MCP_AUTH_TOKEN`) on every request except `/health`; a request with a missing or wrong
  token gets `401`, and if the server has no token configured at all it fails closed (`500`)
  rather than silently running unauthenticated.

## Transport and deployment

The server supports two transports, chosen via `MCP_TRANSPORT`:

- **`stdio`** (default in the package, *not* what Docker uses) — for a developer running
  `mcp-server` directly on their own machine (e.g. wiring it into an MCP inspector or Claude
  Desktop for manual tool testing). stdio requires a parent-spawns-child process relationship,
  which two separate Docker Compose services don't have, so this transport is never used inside
  a container.
- **`streamable-http`** — what both `docker-compose.yml` and any cloud deployment actually use,
  including a **Google Cloud Run** target, since ai-service and mcp-server are always separate
  containers/services talking over the network, never a parent/child process pair. The
  `mcp-server` Dockerfile sets `MCP_TRANSPORT=streamable-http` so this is automatic.
  This is the current MCP HTTP transport, not the deprecated HTTP+SSE transport, and it runs in
  **stateless mode** (`stateless_http=True`): every tool call is a self-contained
  request/response with no server-side session held open between calls. That matters
  specifically for Cloud Run, which bills per-request wall-clock time and wants to freely scale
  an idle service to zero instances — a stateful session (or the old SSE transport, which relies
  on a long-lived connection) is exactly what would prevent that. See
  [ADR 0001, D2](adr/0001-architecture-and-tech-stack.md#d2-mcp-server-built-on-fastmcp-2x-streamable-http-in-stateless-mode-no-sse).

In HTTP mode the server reads `PORT` from the environment (falling back to `MCP_HTTP_PORT`),
matching Cloud Run's convention of injecting `PORT` at runtime. See
[setup.md](setup.md#cloud-deployment) for deployment steps to both a single VM and Cloud Run.
