"""ai-service's only path to Chatwoot: MCP tool calls against mcp-server. No direct Chatwoot
API call exists anywhere else in this service -- see docs/architecture.md."""

from __future__ import annotations

from typing import Any

from fastmcp import Client

from app.config import settings


class MCPToolError(Exception):
    """Raised when an MCP tool call could not be completed at all -- bad arguments, an
    unreachable server, an auth failure, an unknown tool name. Distinct from a Chatwoot-side
    error, which tools return as a structured {"error": True, ...} dict instead of raising."""


async def call_tool(name: str, **arguments: Any) -> dict:
    auth = settings.mcp_auth_token or None
    try:
        async with Client(settings.mcp_server_url, auth=auth) as client:
            result = await client.call_tool(name, arguments)
    except Exception as exc:
        # Deliberately broad: fastmcp/httpx/mcp raise several distinct exception types
        # (ValidationError, ToolError, NotFoundError, httpx.HTTPStatusError, connection
        # errors...) none of which share one common base worth enumerating here. Every one
        # of them means the same thing to a caller: this tool call didn't happen.
        raise MCPToolError(f"MCP tool '{name}' failed: {exc}") from exc

    if result.structured_content is not None:
        return result.structured_content
    if result.data is not None:
        return result.data if isinstance(result.data, dict) else {"result": result.data}
    return {}
