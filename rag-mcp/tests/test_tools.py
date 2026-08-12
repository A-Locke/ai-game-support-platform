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


async def test_related_documents_returns_links_and_backlinks_tagged_with_direction(monkeypatch):
    monkeypatch.setattr(tools, "get_pool", lambda: _async_return("fake-pool"))

    async def _fake_links(pool, source_path):
        assert source_path == "known-issues/ki-014.md"
        return [{"source_path": "faq/general.md", "title": "FAQ", "relation_type": "link"}]

    async def _fake_backlinks(pool, source_path):
        assert source_path == "known-issues/ki-014.md"
        return [{"source_path": "release-notes/1.4.0.md", "title": "Release 1.4.0", "relation_type": "link"}]

    monkeypatch.setattr(tools, "get_links", _fake_links)
    monkeypatch.setattr(tools, "get_backlinks", _fake_backlinks)

    result = await tools.related_documents("known-issues/ki-014.md")

    assert result["source_path"] == "known-issues/ki-014.md"
    assert result["links"] == [{"source_path": "faq/general.md", "title": "FAQ", "relation_type": "link", "direction": "outgoing"}]
    assert result["backlinks"] == [
        {"source_path": "release-notes/1.4.0.md", "title": "Release 1.4.0", "relation_type": "link", "direction": "incoming"}
    ]


async def test_related_documents_empty_when_no_relationships(monkeypatch):
    monkeypatch.setattr(tools, "get_pool", lambda: _async_return("fake-pool"))
    monkeypatch.setattr(tools, "get_links", lambda pool, source_path: _async_return([]))
    monkeypatch.setattr(tools, "get_backlinks", lambda pool, source_path: _async_return([]))

    result = await tools.related_documents("faq/isolated.md")

    assert result == {"source_path": "faq/isolated.md", "links": [], "backlinks": []}


async def _async_return(value):
    return value
