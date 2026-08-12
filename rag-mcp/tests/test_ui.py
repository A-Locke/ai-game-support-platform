import datetime

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from app import ui


def _make_client() -> TestClient:
    app = Starlette(
        routes=[
            Route("/ui", ui.ui_index, methods=["GET"]),
            Route("/ui/documents", ui.ui_create_document, methods=["POST"]),
            Route("/ui/documents/delete", ui.ui_delete_document, methods=["POST"]),
            Route("/ui/search", ui.ui_search, methods=["GET"]),
            Route("/ui/graph", ui.ui_graph, methods=["GET"]),
            Route("/ui/graph-data", ui.ui_graph_data, methods=["GET"]),
            Route("/ui/vault-download", ui.ui_vault_download, methods=["GET"]),
        ]
    )
    return TestClient(app)


def _doc(source_path="known-issues/ki-014.md", title="Large export crash"):
    return {
        "source_path": source_path,
        "title": title,
        "content": "Full content here",
        "indexed_at": datetime.datetime(2026, 8, 11, 12, 0, tzinfo=datetime.timezone.utc),
    }


async def _async_return(value):
    return value


def test_index_lists_documents(monkeypatch):
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))

    async def _fake_list(pool):
        return [_doc()]

    monkeypatch.setattr(ui, "list_documents", _fake_list)
    monkeypatch.setattr(ui, "get_all_links", lambda pool: _async_return([]))

    client = _make_client()
    response = client.get("/ui")

    assert response.status_code == 200
    assert "Large export crash" in response.text
    assert "known-issues/ki-014.md" in response.text


def test_index_shows_backlinks_for_linked_documents(monkeypatch):
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))
    monkeypatch.setattr(ui, "list_documents", lambda pool: _async_return([_doc()]))

    async def _fake_all_links(pool):
        return [
            {
                "source_path": "faq/general-faq.md",
                "target_path": "known-issues/ki-014.md",
                "relation_type": "link",
                "source_title": "General FAQ",
                "target_title": "Large export crash",
            }
        ]

    monkeypatch.setattr(ui, "get_all_links", _fake_all_links)

    client = _make_client()
    response = client.get("/ui")

    assert "Linked from: General FAQ" in response.text


def test_index_omits_backlinks_line_when_none(monkeypatch):
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))
    monkeypatch.setattr(ui, "list_documents", lambda pool: _async_return([_doc()]))
    monkeypatch.setattr(ui, "get_all_links", lambda pool: _async_return([]))

    client = _make_client()
    response = client.get("/ui")

    assert "Linked from:" not in response.text


def test_create_document_rejects_missing_fields(monkeypatch):
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))
    monkeypatch.setattr(ui, "list_documents", lambda pool: _async_return([]))

    client = _make_client()
    response = client.post("/ui/documents", data={"title": "", "category": "faq", "content": ""}, follow_redirects=False)

    assert response.status_code == 303
    assert "error=1" in response.headers["location"]


def test_create_document_embeds_and_upserts_then_redirects(monkeypatch):
    monkeypatch.setattr(ui, "embed_one", lambda text: [0.1, 0.2])
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))

    captured = {}

    async def _fake_upsert(pool, source_path, title, content, embedding):
        captured["args"] = (source_path, title, content, embedding)

    monkeypatch.setattr(ui, "upsert_document", _fake_upsert)

    client = _make_client()
    response = client.post(
        "/ui/documents",
        data={"title": "New known issue", "category": "known-issues", "content": "Description here"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "error" not in response.headers["location"]
    source_path, title, content, embedding = captured["args"]
    assert source_path.startswith("ui/known-issues/new-known-issue-")
    assert title == "New known issue"
    assert content == "Description here"
    assert embedding == [0.1, 0.2]


def test_create_document_accepts_md_file_upload(monkeypatch):
    monkeypatch.setattr(ui, "embed_one", lambda text: [0.1])
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))

    captured = {}

    async def _fake_upsert(pool, source_path, title, content, embedding):
        captured["content"] = content

    monkeypatch.setattr(ui, "upsert_document", _fake_upsert)

    client = _make_client()
    response = client.post(
        "/ui/documents",
        data={"title": "Uploaded doc", "category": "faq"},
        files={"content_file": ("notes.md", b"# Heading\n\nBody text from the file.", "text/markdown")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "error" not in response.headers["location"]
    assert captured["content"] == "# Heading\n\nBody text from the file."


def test_create_document_derives_title_from_filename_when_blank(monkeypatch):
    monkeypatch.setattr(ui, "embed_one", lambda text: [0.1])
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))

    captured = {}

    async def _fake_upsert(pool, source_path, title, content, embedding):
        captured["title"] = title

    monkeypatch.setattr(ui, "upsert_document", _fake_upsert)

    client = _make_client()
    response = client.post(
        "/ui/documents",
        data={"title": "", "category": "faq"},
        files={"content_file": ("password-reset-flow.md", b"Body text", "text/markdown")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "error" not in response.headers["location"]
    assert captured["title"] == "password-reset-flow"


def test_create_document_keeps_explicit_title_over_filename(monkeypatch):
    monkeypatch.setattr(ui, "embed_one", lambda text: [0.1])
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))

    captured = {}

    async def _fake_upsert(pool, source_path, title, content, embedding):
        captured["title"] = title

    monkeypatch.setattr(ui, "upsert_document", _fake_upsert)

    client = _make_client()
    client.post(
        "/ui/documents",
        data={"title": "My chosen title", "category": "faq"},
        files={"content_file": ("some-file.md", b"Body text", "text/markdown")},
        follow_redirects=False,
    )

    assert captured["title"] == "My chosen title"


def test_create_document_file_wins_over_pasted_text(monkeypatch):
    monkeypatch.setattr(ui, "embed_one", lambda text: [0.1])
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))

    captured = {}

    async def _fake_upsert(pool, source_path, title, content, embedding):
        captured["content"] = content

    monkeypatch.setattr(ui, "upsert_document", _fake_upsert)

    client = _make_client()
    client.post(
        "/ui/documents",
        data={"title": "X", "category": "faq", "content": "pasted text"},
        files={"content_file": ("notes.md", b"file text", "text/markdown")},
        follow_redirects=False,
    )

    assert captured["content"] == "file text"


def test_create_document_rejects_non_md_file(monkeypatch):
    client = _make_client()
    response = client.post(
        "/ui/documents",
        data={"title": "X", "category": "faq"},
        files={"content_file": ("notes.pdf", b"%PDF-1.4 fake", "application/pdf")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "error=1" in response.headers["location"]
    assert "Only+.md+files" in response.headers["location"]


def test_create_document_rejects_non_utf8_file(monkeypatch):
    client = _make_client()
    response = client.post(
        "/ui/documents",
        data={"title": "X", "category": "faq"},
        files={"content_file": ("notes.md", b"\xff\xfe not valid utf-8", "text/markdown")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "error=1" in response.headers["location"]
    assert "UTF-8" in response.headers["location"]


def test_create_document_invalid_category_falls_back_to_other(monkeypatch):
    monkeypatch.setattr(ui, "embed_one", lambda text: [0.1])
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))

    captured = {}

    async def _fake_upsert(pool, source_path, title, content, embedding):
        captured["source_path"] = source_path

    monkeypatch.setattr(ui, "upsert_document", _fake_upsert)

    client = _make_client()
    client.post(
        "/ui/documents",
        data={"title": "X", "category": "not-a-real-category", "content": "Y"},
        follow_redirects=False,
    )

    assert captured["source_path"].startswith("ui/other/")


def test_create_document_handles_embedding_failure_gracefully(monkeypatch):
    def _raise(text):
        raise RuntimeError("model not loaded")

    monkeypatch.setattr(ui, "embed_one", _raise)

    client = _make_client()
    response = client.post(
        "/ui/documents", data={"title": "X", "category": "faq", "content": "Y"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert "error=1" in response.headers["location"]


def test_delete_document_success(monkeypatch):
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))

    async def _fake_delete(pool, source_path):
        assert source_path == "known-issues/ki-014.md"
        return True

    monkeypatch.setattr(ui, "delete_document", _fake_delete)

    client = _make_client()
    response = client.post("/ui/documents/delete", data={"source_path": "known-issues/ki-014.md"}, follow_redirects=False)

    assert response.status_code == 303
    assert "error" not in response.headers["location"]


def test_delete_document_not_found(monkeypatch):
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))
    monkeypatch.setattr(ui, "delete_document", lambda pool, source_path: _async_return(False))

    client = _make_client()
    response = client.post("/ui/documents/delete", data={"source_path": "does-not-exist.md"}, follow_redirects=False)

    assert response.status_code == 303
    assert "error=1" in response.headers["location"]


def test_search_renders_ranked_results(monkeypatch):
    monkeypatch.setattr(ui, "embed_one", lambda text: [0.1])
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))
    monkeypatch.setattr(ui, "list_documents", lambda pool: _async_return([]))
    monkeypatch.setattr(ui, "get_all_links", lambda pool: _async_return([]))

    async def _fake_search(pool, query_embedding, top_k):
        return [{"source_path": "faq/x.md", "title": "Two-factor auth", "content": "Settings > Security > 2FA", "score": 0.87}]

    monkeypatch.setattr(ui, "search", _fake_search)

    client = _make_client()
    response = client.get("/ui/search", params={"q": "how do I enable 2fa"})

    assert response.status_code == 200
    assert "Two-factor auth" in response.text
    assert "0.87" in response.text


def test_search_with_empty_query_shows_index_without_searching(monkeypatch):
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))
    monkeypatch.setattr(ui, "list_documents", lambda pool: _async_return([]))
    monkeypatch.setattr(ui, "get_all_links", lambda pool: _async_return([]))
    called = False

    async def _fake_search(pool, query_embedding, top_k):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(ui, "search", _fake_search)

    client = _make_client()
    response = client.get("/ui/search", params={"q": ""})

    assert response.status_code == 200
    assert called is False


def test_document_title_is_html_escaped(monkeypatch):
    # Jinja2 autoescape must be on -- a title containing HTML must not be rendered raw
    # (stored/reflected XSS risk given QA/CS-submitted content is rendered back to other viewers).
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))
    monkeypatch.setattr(ui, "list_documents", lambda pool: _async_return([_doc(title="<script>alert(1)</script>")]))
    monkeypatch.setattr(ui, "get_all_links", lambda pool: _async_return([]))

    client = _make_client()
    response = client.get("/ui")

    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_create_document_resolves_wikilinks(monkeypatch):
    monkeypatch.setattr(ui, "embed_one", lambda text: [0.1])
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))
    monkeypatch.setattr(ui, "upsert_document", lambda pool, source_path, title, content, embedding: _async_return(None))

    captured = {}

    async def _fake_replace_links(pool, source_path, target_titles):
        captured["args"] = (source_path, target_titles)
        return target_titles

    monkeypatch.setattr(ui, "replace_links", _fake_replace_links)

    client = _make_client()
    response = client.post(
        "/ui/documents",
        data={"title": "New FAQ", "category": "faq", "content": "See [[Large export crash]] for details."},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "error" not in response.headers["location"]
    source_path, target_titles = captured["args"]
    assert source_path.startswith("ui/faq/new-faq-")
    assert target_titles == ["Large export crash"]


def test_create_document_skips_link_resolution_when_no_wikilinks(monkeypatch):
    monkeypatch.setattr(ui, "embed_one", lambda text: [0.1])
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))
    monkeypatch.setattr(ui, "upsert_document", lambda pool, source_path, title, content, embedding: _async_return(None))

    called = False

    async def _fake_replace_links(pool, source_path, target_titles):
        nonlocal called
        called = True

    monkeypatch.setattr(ui, "replace_links", _fake_replace_links)

    client = _make_client()
    client.post(
        "/ui/documents",
        data={"title": "Plain doc", "category": "faq", "content": "No links in here."},
        follow_redirects=False,
    )

    assert called is False


def test_graph_page_renders_and_references_cytoscape(monkeypatch):
    client = _make_client()
    response = client.get("/ui/graph")

    assert response.status_code == 200
    assert "cytoscape" in response.text.lower()
    assert "/ui/graph-data" in response.text


def test_graph_data_returns_nodes_and_edges(monkeypatch):
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))
    monkeypatch.setattr(ui, "list_documents", lambda pool: _async_return([_doc()]))

    async def _fake_all_links(pool):
        return [
            {
                "source_path": "known-issues/ki-014.md",
                "target_path": "known-issues/ki-014.md",
                "relation_type": "link",
                "source_title": "Large export crash",
                "target_title": "Large export crash",
            }
        ]

    monkeypatch.setattr(ui, "get_all_links", _fake_all_links)

    client = _make_client()
    response = client.get("/ui/graph-data")

    assert response.status_code == 200
    data = response.json()
    assert data["nodes"] == [{"id": "known-issues/ki-014.md", "label": "Large export crash", "category": "known-issues"}]
    assert data["edges"] == [{"source": "known-issues/ki-014.md", "target": "known-issues/ki-014.md", "relation": "link"}]


def test_infer_category_matches_known_prefixes():
    assert ui._infer_category("known-issues/ki-014.md") == "known-issues"
    assert ui._infer_category("ui/faq/some-doc-abc123.md") == "faq"
    assert ui._infer_category("release-notes/1.4.0.md") == "release-notes"
    assert ui._infer_category("something-else/doc.md") == "other"


def test_vault_download_returns_zip_with_attachment_headers(monkeypatch):
    monkeypatch.setattr(ui, "get_pool", lambda: _async_return("pool"))

    async def _fake_build_vault_zip(pool):
        assert pool == "pool"
        return b"fake-zip-bytes"

    monkeypatch.setattr(ui, "build_vault_zip", _fake_build_vault_zip)

    client = _make_client()
    response = client.get("/ui/vault-download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == "attachment; filename=obsidian-vault-export.zip"
    assert response.content == b"fake-zip-bytes"
