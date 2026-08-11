# ADR 0006: Knowledge-Base RAG (pgvector + fastembed)

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-11 |
| **Related** | [ADR 0004](0004-issue-tracker-grounding.md) · [ai-workflows.md](../ai-workflows.md) |

## Context

The classification prompt's knowledge-base grounding (`ai-service/app/knowledge.py`) has always
worked by concatenating every file under `knowledge-base/known-issues/` and `faq/` into every
prompt, truncated per-file. That doesn't scale — a real deployment with dozens of known issues
would dump all of them into every classification call regardless of relevance, wasting tokens and
diluting what the model actually needs to see. Real semantic search (the design-doc RAG piece
explicitly deferred in ADR 0004) fixes this properly: retrieve only the top-K genuinely relevant
documents for the conversation at hand. Jira/Azure DevOps aren't set up for this portfolio project
(no real credentials — ADR 0004), so this round focuses on RAG over the project's own
`knowledge-base/` corpus instead.

## Decision Drivers

1. **No new infrastructure if existing infrastructure already covers it** — same reasoning as
   ADR 0002's backup service reusing the `pgvector/pgvector:pg16` image already required for
   Chatwoot itself.
2. **Zero recurring cost**, matching this project's cost-conscious portfolio framing.
3. **Narrow, single-purpose MCP servers**, not one server accumulating unrelated concerns — the
   same reasoning that kept Jira/Azure DevOps grounding out of `mcp-server` (ADR 0004) applies to
   knowledge-base search too.
4. **Graceful degradation when unconfigured**, matching every other optional integration in this
   project (S3 backups, Jira/Azure DevOps grounding).

## Decisions

### D1: pgvector, in its own schema, in the same Postgres instance Chatwoot already uses

**Decision:** A new `rag` schema (`rag.documents`) in the existing `postgres` service — not a new
database container, not a separate managed vector DB.

**Why:** `pgvector/pgvector:pg16` is already running specifically because Chatwoot's own schema
requires the `vector` extension (PROJECT_JOURNAL.md, Milestone 1) — genuinely zero new
infrastructure, already covered by the S3 backup/restore path (ADR 0002). At this corpus size
(a handful to low hundreds of documents), pgvector's plain cosine-distance search (`<=>`, no
ANN index) is more than fast enough — confirmed live (see PROJECT_JOURNAL.md, Milestone 8). A
dedicated vector DB (Pinecone, Qdrant, Weaviate, self-hosted or managed) would be real
infrastructure this project's own scope constraints already rule out ("vector databases unless
clearly required" — not clearly required here).

### D2: `fastembed` for local, zero-cost embeddings — not an API provider

**Decision:** Embeddings are generated locally via `fastembed` (ONNX Runtime, not full PyTorch),
using its default model, `BAAI/bge-small-en-v1.5` (384 dimensions, ~67 MB).

**Why:** Zero ongoing cost, zero new API key/vendor, fully self-hosted — evaluated directly
against OpenAI's `text-embedding-3-small` and Voyage AI (Anthropic's own recommended embeddings
partner) and chosen specifically to avoid adding a second AI vendor to an otherwise Claude-centric,
self-hosted-by-default project. ONNX Runtime (not PyTorch) keeps the image lean — `fastembed`
avoids the multi-hundred-MB-to-multi-GB `torch` dependency a `sentence-transformers`-based
approach would pull in.

### D3: A new, separate `rag-mcp` server — not a new tool on `mcp-server`

**Decision:** Knowledge-base search is `rag-mcp/`, its own self-hosted MCP server (mirroring
`mcp-server`'s structure: `fastmcp`, stateless Streamable HTTP, bearer auth, Cloud Run-ready),
not `search_knowledge_base` bolted onto `mcp-server`.

**Why:** `mcp-server` is scoped as a Chatwoot abstraction (docs/mcp-server.md); knowledge-base
search is an unrelated concern with its own data store and its own failure modes. Same reasoning
ADR 0004 used to keep Jira/Azure DevOps grounding as a direct `ai-service` MCP-client integration
rather than folding it into `mcp-server` — and the same reasoning `docs/architecture.md`'s
"Future integration direction" section already anticipated ("a future QA MCP server could sit
alongside this support MCP server as a peer").

### D4: The embedding model is baked into the Docker image at build time

**Decision:** `rag-mcp/Dockerfile` runs a build step that instantiates `TextEmbedding()` once
during the image build (triggering the model download), rather than downloading it on first use
at container startup.

**Why:** Confirmed live that model load (download + ONNX session init) takes ~10 seconds on a
cold cache — acceptable once at build time, not acceptable as every-container-start latency, and
this also means the running container has no runtime dependency on Hugging Face Hub being
reachable.

### D5: Re-index on container startup, plus an on-demand `reindex_knowledge_base` tool

**Decision:** `rag-mcp` walks `knowledge-base/known-issues/`, `faq/`, and `release-notes/` and
(re)embeds everything once at startup. A `reindex_knowledge_base()` MCP tool exposes the same
operation on demand, without a container restart.

**Why:** At this corpus size, full re-indexing on every startup is cheap and avoids the real
complexity of file-watching or incremental-diff indexing, which isn't justified for a handful of
markdown files. The on-demand tool exists for the realistic case of adding/editing a
knowledge-base file without wanting to restart the container.

### D6: One embedding per file, not chunked

**Decision:** Each knowledge-base file gets exactly one embedding vector (title + full content),
not split into multiple chunks.

**Why:** Files here are already short — `knowledge.py`'s existing per-file truncation cap (1500
chars) reflects that this corpus is deliberately small, FAQ-and-known-issue-sized documents, not
long-form design docs that would need chunking to embed meaningfully. Revisit if a future corpus
(the still-deferred actual design-doc case) needs it.

### D7: `ai-service` falls back to the flat knowledge-base dump when RAG isn't configured

**Decision:** `RAG_MCP_URL` unset means `claude_client.py` keeps using
`knowledge.load_knowledge_excerpt()` (the original flat-dump behavior) exactly as before; set,
it uses `rag-mcp`'s `search_knowledge_base` tool for the top-K relevant documents instead.

**Why:** Same graceful-degradation pattern as every other optional integration in this project
(S3 backups, Jira/Azure DevOps grounding) — nothing breaks for anyone who hasn't set up the new
service, and the existing behavior remains a legitimate (if less scalable) fallback rather than
being deleted.

## Consequences (Overall)

**Positive:** Real, live-verified semantic relevance ranking (not just "it runs") replaces a
flat context dump that doesn't scale past a handful of documents; zero new recurring cost; zero
new external vendor; reuses infrastructure the project already pays for.

**Negative / accepted trade-offs:** `fastembed`'s local ONNX model is smaller/cheaper than a
hosted embeddings API but likely lower quality on nuanced semantic matches than a larger hosted
model — an acceptable trade for a zero-cost, self-hosted portfolio deployment. Re-indexing on
every startup would not scale to a large real corpus; revisit (incremental indexing, or a real
design-doc corpus with chunking) if this moves beyond demo scale.
