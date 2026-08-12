"""Entry point. Indexes the knowledge base once at startup (docs/adr/0006, D5), then serves
stdio (local ad-hoc use) or streamable-http (Docker/Cloud Run -- see mcp-server/app/server.py
for the identical reasoning).

Everything runs inside one asyncio.run() call -- startup indexing and the server itself share
the same event loop. Found live: running the initial reindex via its own asyncio.run() call
(closing that loop when done) and then starting uvicorn separately left the asyncpg connection
pool bound to a closed event loop, and the first real tool call failed with "cannot perform
operation: another operation is in progress". See PROJECT_JOURNAL.md, Milestone 8.
"""

from __future__ import annotations

import asyncio
import os

import structlog

from app.config import settings
from app.indexer import reindex
from app.tools import mcp

logger = structlog.get_logger(__name__)


async def _index_at_startup() -> None:
    try:
        count = await reindex()
        logger.info("startup_index_complete", count=count)
    except Exception as exc:  # noqa: BLE001 -- a bad initial index shouldn't crash the server;
        # search_knowledge_base will just return no/stale results until reindex_knowledge_base
        # is called successfully.
        logger.error("startup_index_failed", error=str(exc))


async def _run_stdio() -> None:
    await _index_at_startup()
    await mcp.run_async()


async def _run_http() -> None:
    await _index_at_startup()

    import uvicorn
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    from app.auth import BasicAuthMiddleware, BearerAuthMiddleware
    from app.ui import ui_create_document, ui_delete_document, ui_index, ui_search

    async def health(request):
        return JSONResponse({"status": "ok"})

    # /ui/* routes must be listed before the catch-all Mount("/", mcp_app) below -- Starlette
    # tries routes in order, so anything not matched here (in practice just /mcp) falls through
    # to the mount. Confirmed with a real Starlette TestClient before wiring this in for real.
    mcp_app = mcp.http_app(stateless_http=True)
    app = Starlette(
        routes=[
            Route("/health", health),
            Route("/ui", ui_index, methods=["GET"]),
            Route("/ui/documents", ui_create_document, methods=["POST"]),
            Route("/ui/documents/delete", ui_delete_document, methods=["POST"]),
            Route("/ui/search", ui_search, methods=["GET"]),
            Mount("/", app=mcp_app),
        ],
        lifespan=mcp_app.lifespan,
    )
    app.add_middleware(
        BearerAuthMiddleware,
        expected_token=settings.auth_token,
        unprotected_paths={"/health"},
        unprotected_prefixes=("/ui",),
    )
    app.add_middleware(
        BasicAuthMiddleware,
        username=settings.ui_username,
        expected_password=settings.ui_password,
        protected_prefix="/ui",
    )

    port = int(os.environ.get("PORT", settings.http_port))
    config = uvicorn.Config(app, host=settings.http_host, port=port)
    server = uvicorn.Server(config)
    await server.serve()


def main() -> None:
    if settings.transport != "streamable-http":
        asyncio.run(_run_stdio())
    else:
        asyncio.run(_run_http())


if __name__ == "__main__":
    main()
