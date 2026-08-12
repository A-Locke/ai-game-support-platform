# ADR 0007: Knowledge-Base Ingestion UI

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-11 |
| **Related** | [ADR 0006](0006-knowledge-base-rag.md) |

## Context

ADR 0006 built real semantic search over `knowledge-base/`, but the only way to add a document
was still a filesystem edit (add a `.md` file under the right subdirectory) plus an MCP call to
`reindex_knowledge_base`. That's fine for the person deploying the stack; it's a real barrier
for the people who actually *have* the knowledge worth adding — QA and customer support staff,
who have no reason to touch a server filesystem or an MCP client. The project owner asked for a
small UI aimed specifically at that audience, to eliminate that human handoff.

This is, deliberately, the **first UI anywhere in this project**. The brief scopes out "a custom
frontend replacing Chatwoot" (§18) — that constraint is about not rebuilding the *support agent's*
interface, which Chatwoot already owns. A small internal tool for a completely different
audience (QA/CS adding source material, not agents handling conversations) is a different
question, and the project owner made the call explicitly rather than this being assumed.

## Decisions

### D1: Served by `rag-mcp` itself, not a new service

**Decision:** The UI is a handful of additional Starlette routes (`/ui`, `/ui/documents`,
`/ui/search`) on the *same* app `rag-mcp` already runs for the MCP HTTP transport — not a new
container, not a separate frontend framework.

**Why:** Same reasoning as every infrastructure decision in this project so far (reuse before
adding) — `rag-mcp` already has a Starlette app, already talks to the embeddings model and
Postgres. A dedicated frontend service for what's fundamentally three small forms would be new
infrastructure with no real benefit over three more routes on an app that already exists.

### D2: Server-rendered HTML, no JS framework, no build step

**Decision:** Plain Jinja2 templates, plain HTML forms, full-page submits. No React/Vue/htmx, no
frontend build pipeline, minimal inline CSS.

**Why:** "Tiny frontend" was the ask. Three forms (add a document, delete a document, test a
search) don't need a SPA framework, and a build step would be the first one anywhere in a
project that has otherwise stayed dependency-light throughout (backend Python everywhere else).

### D3: Documents added via the UI live only in Postgres — no file is written

**Decision:** `POST /ui/documents` embeds the submitted text and upserts it directly into
`rag.documents` (same table ADR 0006 already uses), with a synthetic `source_path` like
`ui/<category>/<slug>-<short-id>.md`. It does not write a file into `knowledge-base/` on disk.

**Why:** `knowledge-base/` is baked into both the `ai-service` and `rag-mcp` Docker images at
build time (ADR 0001/0006) — a file written into a running container's copy would vanish on the
next rebuild/redeploy, and making it durable would mean mounting `knowledge-base/` as a shared
read-write volume across two services, a real increase in moving parts for no benefit once
Postgres (already the source of truth for search, already covered by the S3 backup path) can
just hold the content directly. UI-added documents get backup/restore coverage for free as a
result — see [ADR 0002](0002-postgres-backup-and-recovery.md).

**Consequence:** `ai-service`'s flat-file fallback (`knowledge.load_knowledge_excerpt()`, used
only when `RAG_MCP_URL` is unset — ADR 0006, D7) will never see UI-added documents, since it only
reads files. Accepted: nobody would run the ingestion UI in a deployment that has RAG disabled in
the first place, so this gap only matters in a configuration nobody would actually use.

### D4: HTTP Basic Auth, a separate credential from the MCP bearer token

**Decision:** `/ui/*` routes are gated by HTTP Basic Auth (`RAG_UI_USERNAME`/`RAG_UI_PASSWORD`),
checked by a new `BasicAuthMiddleware` — a different mechanism and a different credential from
`RAG_AUTH_TOKEN`, which continues to protect only `/mcp`.

**Why:** The two audiences are genuinely different. `RAG_AUTH_TOKEN` authenticates *services*
(`ai-service`, a Claude Code session) presenting a bearer token they were configured with. A QA
or CS person in a browser has no natural way to attach a bearer header — HTTP Basic Auth is the
simplest mechanism a browser handles natively (its own login prompt, no session/cookie code to
write), appropriate for a small internal tool. Like every other auth check in this project, it
fails closed: an unset `RAG_UI_PASSWORD` returns `500`, never silently-open. Password comparison
uses `secrets.compare_digest` (timing-safe), the same standard this project should have been
holding the original `MCP_AUTH_TOKEN`/`RAG_AUTH_TOKEN` bearer checks to — noted here as an
observation, not fixed retroactively in this ADR's scope.

### D5: The UI can add and delete documents, and includes a self-serve search test

**Decision:** Beyond add/delete, `/ui/search` lets a QA/CS user run the same
`search_knowledge_base` query `ai-service`/the Claude-routine mode would run, and see the ranked
results, directly.

**Why:** Directly serves the stated goal ("eliminate one human step") — without this, confirming
a newly-added document is actually being found requires asking an engineer to check. With it,
the person who added the document can verify it themselves.

### D6: File upload as an alternative to pasting text, gated to `.md` only

**Decision:** `POST /ui/documents` accepts an optional file (`content_file`) alongside the
existing textarea. If a file is present, its extension must be `.md` (case-insensitive) or the
request is rejected with an error message; its decoded UTF-8 content replaces whatever was
pasted into the textarea. No other extension is accepted yet.

**Why:** QA/CS staff often already have the content as a file (a known-issue writeup, release
notes) rather than something they'd retype into a browser textarea. Restricting to `.md` for now
keeps the surface area small — no document-format conversion (`.docx`, `.pdf`, etc.) to get
wrong, no risk of accidentally ingesting binary content as if it were text. The upload still
never touches disk (consistent with D3) — it's read into memory, decoded, and embedded exactly
like pasted text. If the title field is left blank, it's derived from the filename (minus the
`.md` extension) both client-side (a small inline `onchange` handler, so the user sees it happen)
and server-side (so the behavior holds even without JS, e.g. a direct form POST) — an explicitly
typed title always wins over the filename.

## Consequences (Overall)

**Positive:** QA/CS staff can add, remove, and verify knowledge-base content without filesystem
or MCP access — the actual human step this was meant to eliminate. No new service, no new
frontend framework, no new backup surface (Postgres already covers it).

**Negative / accepted trade-offs:** This is the first UI in the project and the first place HTML
templating/form handling exists at all — a small but real increase in `rag-mcp`'s surface area
compared to being a pure MCP server. UI-added documents are invisible to the flat-file fallback
path (D3) — acceptable given that path is only used when RAG itself is disabled.
