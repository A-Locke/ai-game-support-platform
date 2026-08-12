import base64

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.auth import BasicAuthMiddleware, BearerAuthMiddleware


async def _ok(request):
    return JSONResponse({"ok": True})


def _basic_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


def _make_app(*, bearer_token: str, ui_password: str) -> Starlette:
    app = Starlette(routes=[Route("/health", _ok), Route("/mcp", _ok), Route("/ui", _ok), Route("/ui/documents", _ok)])
    app.add_middleware(
        BearerAuthMiddleware, expected_token=bearer_token, unprotected_paths={"/health"}, unprotected_prefixes=("/ui",)
    )
    app.add_middleware(BasicAuthMiddleware, username="admin", expected_password=ui_password, protected_prefix="/ui")
    return app


def test_health_is_unprotected_by_either_scheme():
    client = TestClient(_make_app(bearer_token="secret", ui_password="pw"))
    assert client.get("/health").status_code == 200


def test_mcp_path_requires_bearer_not_basic():
    client = TestClient(_make_app(bearer_token="secret", ui_password="pw"))
    assert client.get("/mcp").status_code == 401
    assert client.get("/mcp", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/mcp", headers={"Authorization": "Bearer secret"}).status_code == 200
    # Basic auth on the bearer-protected path shouldn't work either.
    assert client.get("/mcp", headers={"Authorization": _basic_header("admin", "pw")}).status_code == 401


def test_ui_path_is_exempt_from_bearer_but_requires_basic():
    client = TestClient(_make_app(bearer_token="secret", ui_password="pw"))
    no_auth = client.get("/ui")
    assert no_auth.status_code == 401
    assert "WWW-Authenticate" in no_auth.headers

    assert client.get("/ui", headers={"Authorization": _basic_header("admin", "wrong")}).status_code == 401
    assert client.get("/ui", headers={"Authorization": _basic_header("wronguser", "pw")}).status_code == 401
    assert client.get("/ui", headers={"Authorization": _basic_header("admin", "pw")}).status_code == 200


def test_ui_fails_closed_when_password_unconfigured():
    client = TestClient(_make_app(bearer_token="secret", ui_password=""))
    response = client.get("/ui", headers={"Authorization": _basic_header("admin", "anything")})
    assert response.status_code == 500


def test_malformed_basic_header_is_rejected_not_500():
    client = TestClient(_make_app(bearer_token="secret", ui_password="pw"))
    response = client.get("/ui", headers={"Authorization": "Basic not-valid-base64!!"})
    assert response.status_code == 401
