# ADR 0001: Architecture and Technology Stack

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-10 |
| **Related** | [architecture.md](../architecture.md) · [ai-workflows.md](../ai-workflows.md) · [mcp-server.md](../mcp-server.md) · [cost-estimate.md](../cost-estimate.md) |

## Context

This project is a portfolio-quality demonstration of an AI-augmented customer support platform, applicable to any product/company, not a single vertical: **Chatwoot Community Edition** as the support system of record, a separate **AI orchestration** service that watches Chatwoot via webhooks and calls **Claude**, and a self-hosted **MCP server** that is the only path either the AI layer or any future client has into Chatwoot. The originating brief (`ai_augmented_game_support_technical_task.md`, ingested into these docs and removed once that ingestion was complete — see the project journal) was scoped around a game-support example, and specifies the separation principle, the four AI workflows, and the scope constraints; the project was later generalized past that single-vertical framing (see the project journal) since nothing about the architecture is actually game-specific. This ADR records the *implementation-level* decisions the brief left to the implementer, and why each was made.

## Decision Drivers

1. **Replaceability is a hard requirement, not an aspiration.** Chatwoot, Claude, and the MCP server implementation must each be swappable without redesigning the others (brief §2).
2. **Cheap and simple over enterprise-grade.** This is a demo one person runs locally or on a single low-cost VM, not a production SaaS (brief §1, §18).
3. **Official/reliable libraries over hand-rolled protocol code**, especially for MCP (brief §14).
4. **Never let arbitrary model output execute a dangerous operation directly** (brief §5, §10).
5. **A future serverless deployment target for the MCP server** — added mid-build per direction from the project owner: the MCP server should also run cleanly on Google Cloud Run, which bills per-request and needs to scale to zero between calls.

## Decisions

### D1: No vendored `chatwoot/` source folder — official Docker image only

**Decision:** `docker-compose.yml` pulls `chatwoot/chatwoot:latest`. There is no `chatwoot/` directory containing forked Rails source. Chatwoot-specific setup (webhook registration, custom attributes, labels) is a `scripts/` step against Chatwoot's own API, run once after first boot.

**Why:** The brief's suggested repo layout includes a `chatwoot/` folder but explicitly allows structure changes "if the implementation agent has a strong reason" (§13). Vendoring a Rails monolith to hold a handful of config calls would violate brief §14's "use the Chatwoot API rather than modifying Chatwoot's source code" and add a large, unmaintained fork of someone else's codebase for no benefit — every customization here is reachable through the public API.

### D2: MCP server built on `fastmcp` (2.x), Streamable HTTP in stateless mode, no SSE

**Decision:** The MCP server uses the `fastmcp` PyPI package (not the lower-level `mcp` SDK primitives directly), exposes tools via `@mcp.tool()`, and for HTTP deployments calls `mcp.http_app(stateless_http=True)`. It reads `PORT` from the environment (falling back to `MCP_HTTP_PORT`) and never uses the legacy HTTP+SSE transport.

**Why:** Brief §14 asks for "official/reliable MCP libraries where appropriate rather than implementing the MCP protocol manually" and §4 asks for HTTP deployment support "if practical." `fastmcp` is the same library already proven working for exactly this stdio+Cloud-Run shape in two sibling projects (`UseResponse`, `UnrealTestRail`'s MCP work) — reusing a validated pattern beats reinventing one. Stateless mode matters specifically because Cloud Run bills for wall-clock instance time and wants to scale to zero between requests; the stateful Streamable HTTP mode (and the older SSE transport) both rely on a long-lived server-side session/connection, which is exactly what prevents an instance from ever being safely killed. None of this server's tools need server-initiated push, so nothing is lost by going stateless.

**Consequences:** Every tool call over HTTP is a fully self-contained request — no session state carried between calls on the server side. This is also why idempotency could not live in the MCP server or in ai-service local state (see D5).

### D3: Static bearer token over HTTP, not OAuth

**Decision:** The Streamable HTTP transport is protected by a single shared-secret bearer token (`MCP_AUTH_TOKEN`), checked by a small Starlette middleware. stdio transport (local dev) has no auth — it only ever runs as a trusted child process.

**Why:** `UseResponse`'s MCP server implements a full OAuth 2.0 dance because it's designed to be added as a *remote connector inside claude.ai itself*, which requires OAuth. This server has exactly one intended client — the ai-service — which can be trusted with a long-lived static secret the same way it's trusted with the Chatwoot API token and the Anthropic API key. Building OAuth for a single known caller would be protocol-shaped busywork with no real security benefit here.

### D4: Draft customer-facing responses are stored as private Chatwoot notes, not a bespoke entity

**Decision:** `create_draft_response` writes a private (agent-only) message prefixed `[AI DRAFT]` and tags the conversation `ai-draft`. There is no separate "drafts" table or API.

**Why:** Chatwoot's private notes are already invisible to the customer and visible to agents inside the normal conversation panel — exactly the behavior brief §3.D and §10 require ("store the draft without automatically sending it; make the draft available to the support agent"). Inventing new storage for this would duplicate infrastructure Chatwoot already provides and would need its own agent-facing UI, which is out of scope (§18 rules out a custom frontend).

### D5: Idempotency via a Chatwoot custom attribute, not a local database

**Decision:** Before acting on a conversation, the AI workflow reads a custom attribute (`ai_last_processed_message_id`) via `get_conversation` and skips processing if it already matches the incoming event's message id; on success it writes the new value via `set_conversation_attributes`. No SQLite/Redis dedup store exists in ai-service.

**Why:** An earlier draft of this decision used a local SQLite file for webhook dedup. That breaks under D2/D6's serverless direction: Cloud Run instances are ephemeral and don't share a filesystem, so local dedup state would silently stop working the moment more than one instance (or a fresh cold-started one) handled a retry. Chatwoot is already the durable system of record (brief §2) and is reachable from every request regardless of which instance handles it, so it's the natural place for a dedup marker. This also keeps ai-service itself fully stateless, matching D2's constraint on the MCP server.

**Consequences:** Idempotency now costs one extra `get_conversation` read per webhook, and correctness depends on Chatwoot's custom-attribute write actually landing before a duplicate retry is processed — acceptable at demo scale and traffic; a high-throughput production system would want a proper distributed lock instead.

### D6: ai-service is also built stateless, so it can deploy the same way as the MCP server

**Decision:** ai-service keeps no local state beyond in-memory request handling. It's shipped as a plain Dockerfile that runs equally well as a long-lived container (local Compose, or co-located on the cloud VM) or as a Cloud Run service.

**Why:** Once D5 removed the one piece of local state ai-service had, there was no remaining reason to pin it to the VM. Documenting one deployment shape that works in both places is simpler than maintaining two.

**Consequences:** The default, recommended cloud path (see `docs/setup.md` and `docs/cost-estimate.md`) still runs everything — Chatwoot, ai-service, and mcp-server — via Docker Compose on a single VM, per brief §9's explicit preference for "simple infrastructure" over "unnecessary cloud services." Deploying ai-service and/or mcp-server to Cloud Run instead is documented as an optional variant for whoever wants pay-per-request economics for the low-traffic AI/MCP path while Chatwoot (which is not a good serverless fit — it needs Postgres, Redis, and Sidekiq always reachable) stays on the VM either way.

### D7: Structured Claude output via forced tool-use, not prompt-embedded JSON

**Decision:** Classification/draft calls to Claude use the Messages API with a single forced tool call (`tool_choice={"type": "tool", "name": "record_classification"}`) whose input schema mirrors brief §5's example JSON, rather than asking Claude to emit raw JSON inside a text response.

**Why:** Brief §5 asks the AI layer to "parse structured AI results" and "handle errors and invalid model output," and §12 requires a test for "malformed/invalid Claude output." Forced tool-use makes the model's output schema-constrained at generation time, which is a meaningfully smaller failure surface than parsing free text and just happens to also be simpler code — but the malformed-output path is kept and tested anyway (e.g. a missing required field, or the model declining to call the tool) because brief §12 explicitly asks for that resilience regardless of how much smaller the SDK makes the failure surface.

### D8: MCP tool `get_category_statistics` takes `categories` as a caller-supplied argument

**Decision:** The MCP server has no hardcoded category list. `get_category_statistics(since, until, categories)` treats each category as an opaque Chatwoot label; ai-service owns `SUPPORT_CATEGORIES` (brief §3.B: "the category list should be configuration-driven") and passes it in per call.

**Why:** Baking the category list into the MCP server would put support-workflow business logic into a layer brief §2 says must stay Claude/business-logic-agnostic ("do not put Claude-specific code into the MCP server" — read broadly, this extends to support-workflow-specific business logic like a fixed category taxonomy, not literally just Claude API calls).

### D9: Reporting is two Claude-free MCP calls, then one separate summarization call

**Decision:** `get_support_statistics` and `get_category_statistics` return raw counts only. ai-service's reporting endpoint calls both, then makes a *separate* Claude call to summarize the resulting JSON into prose. Nothing about the MCP tools changes if the summarization step is later swapped for a different LLM or removed entirely.

**Why:** Directly required by brief §3.C: "Separate data retrieval from LLM summarisation."

## Consequences (Overall)

**Positive:** Every component (Chatwoot, ai-service, mcp-server) can be redeployed, restarted, or scaled independently without shared local state to worry about; the MCP server is a genuine drop-in for either a long-lived container or Cloud Run; the category taxonomy and idempotency mechanism both piggyback on infrastructure Chatwoot already provides instead of adding new moving parts.

**Negative / accepted trade-offs:** Idempotency checks cost an extra Chatwoot API round-trip per webhook. The static bearer token (D3) is simpler than OAuth but would need revisiting if this MCP server ever needed to serve an untrusted or multi-tenant client population. Stateless design (D5/D6) is the right call at this project's scale but would need a real distributed-lock or queue-based approach under production write volume.
