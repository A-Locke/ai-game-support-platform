"""Two auth schemes for two audiences (docs/adr/0007, D4): BearerAuthMiddleware protects /mcp
(services presenting a token they were configured with -- ai-service, a Claude Code session).
BasicAuthMiddleware protects /ui/* (a human in a browser -- HTTP Basic is what a browser handles
natively, no session/cookie code needed). Each middleware only acts on the paths it owns and
passes everything else through untouched, so they stack without conflicting.
"""

from __future__ import annotations

import base64
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        expected_token: str,
        unprotected_paths: set[str] | None = None,
        unprotected_prefixes: tuple[str, ...] = (),
    ):
        super().__init__(app)
        self._expected_token = expected_token
        self._unprotected_paths = unprotected_paths or set()
        self._unprotected_prefixes = unprotected_prefixes

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in self._unprotected_paths or path.startswith(self._unprotected_prefixes):
            return await call_next(request)

        if not self._expected_token:
            return JSONResponse({"error": "RAG_AUTH_TOKEN is not configured on the server"}, status_code=500)

        header = request.headers.get("authorization", "")
        if not secrets.compare_digest(header, f"Bearer {self._expected_token}"):
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        return await call_next(request)


class BasicAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, username: str, expected_password: str, protected_prefix: str):
        super().__init__(app)
        self._username = username
        self._expected_password = expected_password
        self._protected_prefix = protected_prefix

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith(self._protected_prefix):
            return await call_next(request)

        if not self._expected_password:
            return JSONResponse({"error": "RAG_UI_PASSWORD is not configured on the server"}, status_code=500)

        challenge = Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="rag-mcp UI"'})

        header = request.headers.get("authorization", "")
        if not header.startswith("Basic "):
            return challenge

        try:
            decoded = base64.b64decode(header[len("Basic ") :]).decode("utf-8")
            username, _, password = decoded.partition(":")
        except Exception:
            return challenge

        username_ok = secrets.compare_digest(username, self._username)
        password_ok = secrets.compare_digest(password, self._expected_password)
        if not (username_ok and password_ok):
            return challenge

        return await call_next(request)
