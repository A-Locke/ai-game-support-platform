from app import rag_client
from app.config import settings


async def test_returns_empty_when_not_configured():
    settings.rag_mcp_url = ""

    result = await rag_client.search_knowledge_base("export crash")

    assert result == ""


async def test_returns_empty_and_logs_on_failure(monkeypatch):
    settings.rag_mcp_url = "http://rag-mcp.test/mcp"

    class _RaisingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            raise RuntimeError("connection refused")

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(rag_client, "Client", _RaisingClient)

    result = await rag_client.search_knowledge_base("export crash")

    assert result == ""


async def test_formats_results_into_text_block(monkeypatch):
    settings.rag_mcp_url = "http://rag-mcp.test/mcp"

    class _FakeResult:
        structured_content = {
            "results": [
                {"title": "KI-014 Large export crash", "content": "Crashes over 10k rows.", "score": 0.91},
            ]
        }
        data = None

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def call_tool(self, name, arguments):
            assert name == "search_knowledge_base"
            assert arguments == {"query": "export crash", "top_k": settings.rag_top_k}
            return _FakeResult()

    monkeypatch.setattr(rag_client, "Client", _FakeClient)

    result = await rag_client.search_knowledge_base("export crash")

    assert "KI-014 Large export crash" in result
    assert "Crashes over 10k rows." in result
    assert "0.91" in result


async def test_empty_results_returns_empty_string(monkeypatch):
    settings.rag_mcp_url = "http://rag-mcp.test/mcp"

    class _FakeResult:
        structured_content = {"results": []}
        data = None

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def call_tool(self, name, arguments):
            return _FakeResult()

    monkeypatch.setattr(rag_client, "Client", _FakeClient)

    result = await rag_client.search_knowledge_base("nothing relevant")

    assert result == ""
