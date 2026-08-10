"""AI-generated reporting (brief §3.C). fetch_report_data and build_report_summary are kept
deliberately separate -- data retrieval has no LLM involvement, summarisation is a single
independent Claude call over the already-fetched data. See ADR 0001, D9."""

from app import mcp_client
from app.claude_client import summarize_report
from app.config import settings


async def fetch_report_data(since: str, until: str) -> dict:
    stats = await mcp_client.call_tool("get_support_statistics", since=since, until=until)
    categories = await mcp_client.call_tool(
        "get_category_statistics", since=since, until=until, categories=settings.categories
    )
    return {**stats, "categories": categories.get("categories", {})}


async def build_report_summary(since: str, until: str) -> dict:
    data = await fetch_report_data(since, until)
    summary = await summarize_report(data)
    return {"data": data, "summary": summary}
