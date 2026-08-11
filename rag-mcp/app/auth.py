"""Bearer-token auth for the Streamable HTTP transport. Identical pattern to mcp-server/app/auth.py
(no shared package between services in this repo, by design -- each service fully owns its code).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, expected_token: str, unprotected_paths: set[str] | None = None):
        super().__init__(app)
        self._expected_token = expected_token
        self._unprotected_paths = unprotected_paths or set()

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self._unprotected_paths:
            return await call_next(request)

        if not self._expected_token:
            return JSONResponse({"error": "RAG_AUTH_TOKEN is not configured on the server"}, status_code=500)

        header = request.headers.get("authorization", "")
        if header != f"Bearer {self._expected_token}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        return await call_next(request)
