"""Optional semantic search over the knowledge base via rag-mcp, instead of
knowledge.load_knowledge_excerpt()'s flat dump. See docs/adr/0006, D7 -- empty RAG_MCP_URL
falls back to the flat dump; a search failure degrades to it too, never blocks classification."""

from __future__ import annotations

import structlog
from fastmcp import Client

from app.config import settings

logger = structlog.get_logger(__name__)


async def search_knowledge_base(query: str) -> str:
    """Returns a formatted text block of the top-K relevant documents, or empty string if RAG
    isn't configured or the search fails -- callers should fall back to the flat dump on empty."""
    if not settings.rag_mcp_url:
        return ""

    try:
        async with Client(settings.rag_mcp_url, auth=settings.rag_mcp_auth_token or None) as client:
            result = await client.call_tool(
                "search_knowledge_base", {"query": query, "top_k": settings.rag_top_k}
            )
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, see module docstring
        logger.warning("rag_search_failed", error=str(exc))
        return ""

    data = result.structured_content or result.data or {}
    results = data.get("results", [])
    if not results:
        return ""

    lines = ["Relevant knowledge-base documents (semantic search):"]
    for item in results:
        lines.append(f"### {item['title']} (relevance {item['score']:.2f})\n{item['content']}")
    return "\n\n".join(lines)
