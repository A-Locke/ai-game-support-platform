from app import tools
from app.config import settings


async def test_search_knowledge_base_embeds_query_and_searches(monkeypatch):
    monkeypatch.setattr(tools, "get_pool", lambda: _async_return("fake-pool"))
    monkeypatch.setattr(tools, "embed_one", lambda text: [0.1, 0.2, 0.3])

    captured = {}

    async def _fake_search(pool, query_embedding, top_k):
        captured["args"] = (pool, query_embedding, top_k)
        return [{"source_path": "known-issues/ki-014.md", "title": "Large export crash", "content": "...", "score": 0.9}]

    monkeypatch.setattr(tools, "search", _fake_search)

    result = await tools.search_knowledge_base("export crashes")

    assert captured["args"] == ("fake-pool", [0.1, 0.2, 0.3], settings.default_top_k)
    assert result["query"] == "export crashes"
    assert result["results"][0]["title"] == "Large export crash"


async def test_search_knowledge_base_respects_explicit_top_k(monkeypatch):
    monkeypatch.setattr(tools, "get_pool", lambda: _async_return("fake-pool"))
    monkeypatch.setattr(tools, "embed_one", lambda text: [0.1])

    captured = {}

    async def _fake_search(pool, query_embedding, top_k):
        captured["top_k"] = top_k
        return []

    monkeypatch.setattr(tools, "search", _fake_search)

    await tools.search_knowledge_base("query", top_k=7)

    assert captured["top_k"] == 7


async def test_reindex_knowledge_base_returns_count(monkeypatch):
    async def _fake_reindex():
        return 5

    monkeypatch.setattr(tools, "reindex", _fake_reindex)

    result = await tools.reindex_knowledge_base()

    assert result == {"indexed": 5}


async def test_index_status_reports_document_count(monkeypatch):
    monkeypatch.setattr(tools, "get_pool", lambda: _async_return("fake-pool"))

    async def _fake_count(pool):
        assert pool == "fake-pool"
        return 12

    monkeypatch.setattr(tools, "count_documents", _fake_count)

    result = await tools.index_status()

    assert result == {"document_count": 12}


async def _async_return(value):
    return value
