"""Entry point. stdio for local ad-hoc tool inspection; streamable-http (stateless) for
every containerized deployment -- see docs/mcp-server.md for why.
"""

from __future__ import annotations

import os

from app.config import settings
from app.tools import mcp


def main() -> None:
    if settings.transport != "streamable-http":
        mcp.run()  # stdio
        return

    import uvicorn
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    from app.auth import BearerAuthMiddleware

    async def health(request):
        return JSONResponse({"status": "ok"})

    # stateless_http=True: no server-side session, every call is a self-contained
    # request/response. Required for Cloud Run's scale-to-zero billing model to make sense --
    # see docs/mcp-server.md.
    mcp_app = mcp.http_app(stateless_http=True)
    app = Starlette(
        routes=[Route("/health", health), Mount("/", app=mcp_app)],
        lifespan=mcp_app.lifespan,
    )
    app.add_middleware(BearerAuthMiddleware, expected_token=settings.auth_token, unprotected_paths={"/health"})

    # Cloud Run injects PORT at runtime; MCP_HTTP_PORT is the local/Compose fallback.
    port = int(os.environ.get("PORT", settings.http_port))
    uvicorn.run(app, host=settings.http_host, port=port)


if __name__ == "__main__":
    main()
