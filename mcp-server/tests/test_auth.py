from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.auth import BearerAuthMiddleware


async def _health(request):
    return JSONResponse({"status": "ok"})


async def _protected(request):
    return JSONResponse({"ok": True})


def _make_app(expected_token: str) -> Starlette:
    app = Starlette(routes=[Route("/health", _health), Route("/mcp", _protected)])
    app.add_middleware(BearerAuthMiddleware, expected_token=expected_token, unprotected_paths={"/health"})
    return app


def test_health_endpoint_is_unprotected():
    client = TestClient(_make_app(expected_token="secret"))
    assert client.get("/health").status_code == 200


def test_missing_bearer_token_is_rejected():
    client = TestClient(_make_app(expected_token="secret"))
    assert client.get("/mcp").status_code == 401


def test_wrong_bearer_token_is_rejected():
    client = TestClient(_make_app(expected_token="secret"))
    response = client.get("/mcp", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_correct_bearer_token_is_accepted():
    client = TestClient(_make_app(expected_token="secret"))
    response = client.get("/mcp", headers={"Authorization": "Bearer secret"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_unconfigured_token_fails_closed():
    client = TestClient(_make_app(expected_token=""))
    response = client.get("/mcp", headers={"Authorization": "Bearer anything"})
    assert response.status_code == 500
