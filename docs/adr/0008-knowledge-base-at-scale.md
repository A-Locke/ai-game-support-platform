# ADR 0008: Designing the Knowledge Base for Scale (Historical/Live Split, Graph-Augmented Retrieval)

| | |
|---|---|
| **Status** | Accepted (design only — see Consequences for what's actually built vs. blueprint) |
| **Date** | 2026-08-12 |
| **Related** | [ADR 0004](0004-issue-tracker-grounding.md) · [ADR 0006](0006-knowledge-base-rag.md) · [ADR 0007](0007-knowledge-base-ingestion-ui.md) |

## Context

ADR 0006/0007 built real semantic search and a QA/CS ingestion UI, but both assume a small,
demo-scale corpus (a handful of `knowledge-base/` files plus whatever's added by hand through
`/ui`). The project owner asked what changes if the real knowledge base is instead the *entire*
history of a real deployment: a full Jira/Azure DevOps issue dump, a real design-doc corpus, and
scraped product-support pages — orders of magnitude larger and structurally heterogeneous. This
ADR captures that design discussion: what changes at scale, which off-the-shelf alternatives were
considered and why they weren't adopted, and which parts of the resulting design are actually
implemented today versus left as a blueprint for when real credentials/data exist.

The target company for this portfolio project uses Azure DevOps specifically (not Jira), which
ruled out relying on Jira-specific tooling as the primary path and shaped D7/D8 below.

## Decision Drivers

1. **Stay self-hosted and zero/low-cost**, consistent with every prior ADR — pgvector in the
   already-running Postgres, local embeddings, no new paid vendor, unless a real gap forces it.
2. **Don't build what can be harvested.** Jira/Azure DevOps already model relationships between
   issues natively (links, parent/child hierarchy) — inventing a manual linking syntax would be
   redundant with data the source system already has.
3. **Stay honest about what's verified.** Per ADR 0004's precedent, anything that can't be
   exercised against real data (no Jira/Azure DevOps credentials exist for this project) must say
   so plainly rather than being presented as tested.

## Options evaluated

| Option | Verdict |
|---|---|
| **Azure-native stack** (Azure DevOps → Logic Apps trigger → Azure AI Search index, replacing pgvector) | Rejected. No first-party Azure AI Search indexer exists for Azure DevOps (the built-in gallery covers Cosmos DB/Blob/Azure SQL/SQL-on-VM only) — this would still mean hand-building the bridge, just on managed Azure services instead of self-hosted ones. Introduces the project's first real recurring cloud cost and vendor lock-in, and branches into cloud-integration-engineering territory distinct from the self-hosted-systems story the rest of this project tells. See discussion in this ADR's history; not written up as its own decision below since it was rejected before reaching implementation-level detail. |
| **Onyx (formerly Danswer)** — open-source, self-hosted enterprise RAG platform with 40+ connectors, hybrid search, reranking | Rejected for now. Genuinely the right *category* of tool (built for exactly this: ingest heterogeneous sources, chunk, hybrid-search), and it has a community MCP bridge that would have slotted into the existing `ai-service` → MCP-server pattern with no new integration style. But it bundles its own Postgres, search backend, Redis, and workers — a real increase in self-hosted operational surface — and its generic File connector (the path that would carry an Azure DevOps *export*, since it has no native ADO connector) is a manual/scripted zip-upload today, not the polished scheduled sync its native connectors get. Adopting it would also replace `rag-mcp` outright rather than extend it, which conflicts with this project's habit of building and documenting its own architecture decisions rather than assembling an existing platform. Worth revisiting if the corpus genuinely outgrows what D5-D9 below can handle. |
| **Apache AGE** (openCypher graph extension for Postgres) as the graph layer | Not adopted now, kept as a named upgrade path (D9). It's the lighter-weight option versus Neo4j specifically because it's a Postgres *extension*, not a new server — but a plain adjacency table already covers the retrieval improvement described in D6 at this corpus size. |
| **Plain adjacency table in the existing Postgres**, harvesting relationships from source systems rather than hand-authoring them | **Chosen** (D6). No new infrastructure, reuses the same `rag` schema and backup path ADR 0006/0007 already established. |

## Decisions

### D1: Two-tier retrieval — bulk-indexed historical data, narrow-scoped live queries for in-progress work

**Decision:** `rag-mcp`'s pgvector store holds everything *settled* (closed/resolved issues,
design docs, scraped support pages). `ai-service/app/grounding.py`'s existing live Jira/Azure
DevOps MCP queries (ADR 0004) stay exactly as built, but their scope narrows to *in-progress*
work only.

**Why:** Historical data is stable — indexing it once (and re-syncing periodically) is efficient
and avoids re-querying the issue tracker live for every classification. In-progress work is
volatile (status changes, gets closed, gets merged as a duplicate) — a live query is right for
that specifically because staleness there would actively mislead a classification (e.g., citing
a duplicate that was actually closed as "not a bug" yesterday).

### D2: The boundary is issue status, not sprint

**Decision:** "In progress" means an open/active status (`Open`, `In Progress`, `In Review`, the
Azure DevOps equivalents), not sprint membership. Sprint/iteration can narrow the live query
further for teams that use it, but isn't the primary signal.

**Why:** Sprint-based scoping only works for Scrum-style boards with a Sprint/Iteration field —
Kanban-style Azure DevOps projects (common, and not something this project can assume away) have
no sprint concept at all. Status is the universal signal both board styles share.

### D3: Sync is a scheduled pull, not a webhook, and reuses the existing idempotent-upsert pattern

**Decision:** A periodic (nightly) job pulls everything whose status transitioned to closed since
the last run and upserts it into `rag.documents` via the existing `upsert_document` (already
`ON CONFLICT ... DO UPDATE` by `source_path`, so re-running is always safe). If a previously
indexed item's status flips back to open (reopened), the same sync pass removes it from the
index — live-query results always take precedence over an indexed copy for the same ticket ID
while it's live, and an indexed copy of something currently in progress would otherwise sit
around giving stale answers to unrelated semantic searches until the next sync caught it.

**Why:** A nightly cron pull matches this project's existing infrastructure style — the S3 backup
already runs as cron-in-container ([ADR 0002](0002-postgres-backup-and-recovery.md)) — rather than
adding a second inbound webhook surface alongside Chatwoot's. Explicitly deciding the
reopened-ticket case here (rather than leaving it implicit) avoids a real correctness bug: two
different answers for the same ticket ID depending on which path served the query.

### D4: One-time historical backfill and ongoing incremental sync are different operations

**Decision:** The initial "index everything ever closed" pass is a large paginated export, better
done as a direct REST API pull than routed through the same MCP tool interface built for small
targeted lookups. The nightly incremental delta ("what closed since yesterday") is small and
recurring, and can reasonably reuse the same official Azure DevOps MCP server D1/ADR 0004 already
depends on. Design docs and scraped support pages have no "in progress" state at all — they're
always bulk, on their own periodic re-scrape/re-index cadence, with no live counterpart.

**Why:** Treating these as the same operation would mean either running a full historical re-scan
nightly (wasteful) or building the bulk export path around the wrong tool (an interface designed
for single-item queries, not pagination-heavy dumps).

### D5: Chunking and metadata are per-source-type, not one-size-fits-all

**Decision:** Short items (individual Azure DevOps work items) are embedded as one chunk each, as
`rag-mcp` already does. Long-form content (design docs, scraped support pages) gets real chunking
— recursive splitting (~512 tokens, 50-100 token overlap) as the default, per current chunking
research. Every chunk carries a `metadata JSONB` column (`source_type`, `status`, `component`,
`issue_type`, etc.), populated from YAML frontmatter for file-based sources and from the source
system's own fields for Azure DevOps items, usable as a pre-filter (SQL `WHERE`) ahead of the
pgvector similarity search.

**Why:** Whole-document embedding (today's `rag-mcp` behavior) only works because the demo corpus
is short files. Metadata-based filtering consistently shows up in current RAG research as
delivering bigger retrieval-quality gains than chunking strategy or embedding-model choice —
worth prioritizing over fancier retrieval tricks.

### D6: Graph edges are harvested from each source's native structure, not hand-authored

**Decision:** A plain adjacency table, `rag.document_links(source_path, target_path,
relation_type)`, in the same Postgres instance (no new database). At real scale, it's populated
from Azure DevOps's own work-item relations (Related, Duplicate, Parent/Child) pulled via the
same official MCP server, plus regex-extracted ticket-ID mentions (`#1234`-style) found in design
docs. Used for two things: deduplicating near-identical historical bug reports (a real problem in
actual issue-tracker dumps), and one-hop expansion — when a semantic search hits a document, its
directly-linked neighbors are pulled in as extra context too.

**Why:** This is the deliberately lightweight version of what "GraphRAG" research does with much
heavier machinery (LLM-driven entity/relationship extraction from unstructured text). Azure
DevOps already hands you a real relationship graph for free through its own data model — building
one via LLM extraction would be redundant cost for data that already exists in structured form.
An early version of this idea (hand-authored Obsidian-style `[[wikilinks]]`) was considered first
and is *also* implemented today (D10) for the demo corpus, where no source system exists to
harvest structure from — but at Azure DevOps dump scale, harvesting (this decision) replaces
hand-authoring entirely; nobody would type link syntax into thousands of tickets.

### D7: Azure-native alternatives were evaluated and rejected

**Decision:** Documented in the Options table above rather than repeated here — not chosen because
it introduces the project's first real cloud vendor cost/lock-in and still requires hand-building
the ADO bridge (no first-party indexer exists), for a different kind of engineering demonstration
than the rest of this project makes.

### D8: Onyx was evaluated and rejected

**Decision:** Also in the Options table — not chosen because it would replace `rag-mcp` with a
materially heavier self-hosted platform (its own Postgres, search backend, Redis, workers) for a
gap (native ADO ingestion) it doesn't actually close any better than D6's harvested-links
approach; ADO would still need a generic file-export workaround either way.

### D9: Apache AGE is a named upgrade path, not adopted now

**Decision:** If D6's plain adjacency table ever stops being sufficient — genuine multi-hop
graph traversal, real graph algorithms, not just one-hop lookups — Apache AGE (an Apache 2.0
openCypher extension *for Postgres itself*, not a separate server) is the next step, specifically
because it stays inside the same instance/connection-pool/backup path rather than adding a
dedicated graph database like Neo4j. Not needed for anything D6 through D11 actually require.

### D10: The demo corpus uses hand-authored `[[wikilinks]]`, resolved by title, unresolved links skipped silently

**Decision:** For the file-based demo corpus and UI-added documents — where there's no source
system to harvest structure from — `rag.document_links` is populated by parsing `[[Target
Title]]` syntax out of document content at index time, resolving each target by case-insensitive
title match against `rag.documents`. A link to a title that doesn't (yet) exist is silently
skipped, not an error — the same "unlinked mention" behavior Obsidian itself has. Resolution is
two-pass on a full `reindex_knowledge_base` call (upsert every document first, then resolve links
against the now-complete title set, so link order doesn't matter); a single `/ui/documents` POST
only resolves against documents that already existed at that moment, so a newly-added document
that other, older documents intended to reference won't show that backlink until the next full
reindex.

**Why:** This is the same mechanism D6 describes for Azure DevOps at scale, just fed by manual
authoring instead of a harvested source, which is exactly right at this corpus size — nobody's
hand-authoring links into thousands of tickets, but a QA/CS person adding one FAQ can absolutely
type `[[Known Issue Title]]` into it. Keeping the underlying table and resolution logic identical
means the retrieval-side code (backlinks, one-hop expansion, the graph view) doesn't need to know
or care whether an edge came from a human or from Azure DevOps's API.

### D11: Graph relationships get a visual layer — an in-app graph view, plus an optional Obsidian export

**Decision:** A `/ui/graph` page in the existing ingestion UI, rendering `rag.document_links` as
nodes/edges via a single vendored, no-build-step JS graph library (no new frontend framework,
consistent with [ADR 0007, D2](0007-knowledge-base-ingestion-ui.md#d2-server-rendered-html-no-js-framework-no-build-step)).
Separately, a small module (`app/export_vault.py`) can dump `rag.documents` +
`rag.document_links` into a folder of real `.md` files with `[[wikilinks]]` matching the harvested
edges, browsable as an actual Obsidian vault for its graph view specifically. Two ways to get it:
a **"Download as Obsidian vault (.zip)"** button right on `/ui` (the same handler zipped in
memory instead of writing to disk, reusing the same Basic Auth `/ui` already has), or, for
whoever's operating the server directly, `docker compose exec` plus `docker compose cp`.

**Why:** The in-app page stays part of the running, demoable system, always current, nothing
separate to open, and is the one worth treating as a real feature. The Obsidian export is close
to free once the links table exists (a read-only, one-way snapshot export, not infrastructure)
and is worth keeping given how directly Obsidian's own model informed D6's shape, but it's a demo
aid, not something the running platform depends on. The download button specifically matters once
the system is actually deployed somewhere remote (a VPS, say): the person who wants to browse the
graph in their own local Obsidian is plausibly QA/CS staff with only a browser and the `/ui`
credentials, the same audience ADR 0007 built the whole ingestion UI for in the first place, not
someone with SSH access to the server. Requiring SSH access for this one feature specifically
would have been an inconsistent bar to set.

## Consequences (Overall)

**What's actually built and live-validated today** (against the existing demo corpus, real
Postgres, real container rebuild — same rigor as every other feature in this project): the
`document_links` schema and its `db.py` functions; `[[wikilink]]`-style parsing and two-pass
resolution in `indexer.py` (works for both the file-based demo corpus and UI-added documents); a
`related_documents` MCP tool; backlinks shown in the ingestion UI; the in-app `/ui/graph` view;
and the Obsidian vault export, both as a CLI script and a one-click `/ui/vault-download` zip.
These don't require Azure DevOps credentials because they operate on whatever's already indexed,
regardless of source.

**What remains a blueprint, not code** (D1-D5, D7's harvested-from-ADO half of D6): the
historical/live split itself, the nightly sync job, per-source-type chunking, metadata-driven
filtering, and pulling real relationship data from Azure DevOps. None of this can be built and
live-verified without a real Azure DevOps instance, which doesn't exist in this project's
environment — consistent with ADR 0004's same honest caveat about its live-grounding code. Picking
this back up for real should start with D1-D3 (the sync job), since everything else assumes it
exists.
