"""MCP tool surface: semantic search over knowledge-base/. See docs/adr/0006."""

from __future__ import annotations

from fastmcp import FastMCP

from app.config import settings
from app.db import count_documents, get_pool, search
from app.embeddings import embed_one
from app.indexer import reindex

mcp = FastMCP(
    name="rag-mcp",
    instructions=(
        "Semantic search over this project's knowledge-base/ (known issues, FAQ, release notes) "
        "via pgvector + local embeddings. search_knowledge_base(query, top_k) returns the most "
        "semantically relevant documents for a query -- use it to ground a classification or "
        "reply in real known-issue/FAQ content instead of guessing. reindex_knowledge_base() "
        "re-embeds the corpus on demand (e.g. after editing a file) without restarting the "
        "server. index_status() reports how many documents are currently indexed."
    ),
)


@mcp.tool()
async def search_knowledge_base(query: str, top_k: int | None = None) -> dict:
    """Semantic search over the knowledge base. Returns the top_k most relevant documents
    (source_path, title, content, score) for the given query."""
    pool = await get_pool()
    query_embedding = embed_one(query)
    results = await search(pool, query_embedding, top_k or settings.default_top_k)
    return {"query": query, "results": results}


@mcp.tool()
async def reindex_knowledge_base() -> dict:
    """Re-embed every file under knowledge-base/known-issues, faq, and release-notes. Safe to
    call repeatedly -- upserts by file path, doesn't duplicate."""
    count = await reindex()
    return {"indexed": count}


@mcp.tool()
async def index_status() -> dict:
    """Report how many documents are currently indexed."""
    pool = await get_pool()
    count = await count_documents(pool)
    return {"document_count": count}
