"""Optional grounding: search real Jira/Azure DevOps issues for existing matches before
classification, instead of relying solely on the static knowledge-base excerpt. Each source is
independently optional (empty *_MCP_URL = skipped) and fails independently -- a tracker outage
degrades to "no extra context," never a crashed or blocked classification. See docs/adr/0004.

Verification caveat (stated in the ADR too, repeating here since it matters): the exact response
*shape* each tool below returns was not verified against a real Jira/Azure DevOps instance --
no credentials for either were available while building this. Parsing is deliberately defensive
(`.get()` with fallbacks, multiple shape guesses) for exactly that reason. Treat your first real
run as the actual verification step.
"""

from __future__ import annotations

import asyncio

import structlog
from fastmcp import Client

from app.config import settings

logger = structlog.get_logger(__name__)


async def _call(url: str, auth: str | None, tool_name: str, arguments: dict) -> dict | list | None:
    async with Client(url, auth=auth) as client:
        result = await client.call_tool(tool_name, arguments)
    if result.structured_content is not None:
        return result.structured_content
    return result.data


async def _search_jira(query: str) -> list[dict]:
    if not settings.jira_mcp_url:
        return []
    jql = f'text ~ "{query}"'
    if settings.jira_jql_project_filter:
        jql = f"{settings.jira_jql_project_filter} AND {jql}"
    try:
        result = await _call(
            settings.jira_mcp_url,
            settings.jira_mcp_api_token or None,
            "searchJiraIssuesUsingJql",
            {"jql": jql, "maxResults": settings.grounding_max_results},
        )
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, see module docstring
        logger.warning("jira_search_failed", error=str(exc))
        return []
    return _normalize_jira(result)


async def _search_azure_devops(query: str) -> list[dict]:
    if not settings.azure_devops_mcp_url:
        return []
    try:
        result = await _call(
            settings.azure_devops_mcp_url,
            settings.azure_devops_mcp_pat or None,
            "mcp_ado_search_workitem",
            {"searchText": query, "top": settings.grounding_max_results},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("azure_devops_search_failed", error=str(exc))
        return []
    return _normalize_ado(result)


def _normalize_jira(result) -> list[dict]:
    """Defensive by design -- see the module-level verification caveat."""
    if result is None:
        return []
    issues = result.get("issues") if isinstance(result, dict) else result
    if not isinstance(issues, list):
        return []
    normalized = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        fields = issue.get("fields", {}) if isinstance(issue.get("fields"), dict) else {}
        key = issue.get("key") or issue.get("id")
        summary = fields.get("summary") or issue.get("summary")
        if not key or not summary:
            continue
        status = fields.get("status", {})
        status_name = status.get("name") if isinstance(status, dict) else status
        normalized.append({"source": "jira", "id": str(key), "summary": summary, "status": status_name})
    return normalized[: settings.grounding_max_results]


def _normalize_ado(result) -> list[dict]:
    """Defensive by design -- see the module-level verification caveat."""
    if result is None:
        return []
    items = None
    if isinstance(result, dict):
        items = result.get("results") or result.get("workItems") or result.get("value")
    elif isinstance(result, list):
        items = result
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        fields = item.get("fields", {}) if isinstance(item.get("fields"), dict) else {}
        item_id = item.get("id")
        title = fields.get("System.Title") or item.get("title")
        if item_id is None or not title:
            continue
        state = fields.get("System.State") or item.get("state")
        normalized.append({"source": "azure_devops", "id": str(item_id), "summary": title, "status": state})
    return normalized[: settings.grounding_max_results]


async def search_related_issues(query: str) -> str:
    """Returns a short text block for prompt inclusion (empty string if nothing configured or
    nothing found -- callers should handle that as "no grounding data available")."""
    jira_results, ado_results = await asyncio.gather(_search_jira(query), _search_azure_devops(query))
    all_results = jira_results + ado_results
    if not all_results:
        return ""

    lines = ["Related existing issues found in the issue tracker(s):"]
    for item in all_results:
        lines.append(f"- [{item['source']} {item['id']}] {item['summary']} (status: {item['status']})")
    return "\n".join(lines)
