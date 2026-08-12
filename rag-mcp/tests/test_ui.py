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

    client = _make_client()
    response = client.get("/ui")

    assert response.status_code == 200
    assert "Large export crash" in response.text
    assert "known-issues/ki-014.md" in response.text


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

    client = _make_client()
    response = client.get("/ui")

    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text
