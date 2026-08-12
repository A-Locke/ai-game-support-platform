"""Ingestion UI for QA/CS staff -- add, remove, and test-search knowledge-base documents without
filesystem or MCP access. See docs/adr/0007. Plain server-rendered HTML, no JS framework (D2)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from app.db import delete_document, get_pool, list_documents, search, upsert_document
from app.embeddings import embed_one

logger = structlog.get_logger(__name__)

_ALLOWED_CATEGORIES = ("known-issues", "faq", "release-notes", "other")

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return (slug or "document")[:60]


async def _render_index(message: str | None = None, error: bool = False, query: str | None = None, search_results=None) -> HTMLResponse:
    pool = await get_pool()
    documents = await list_documents(pool)
    template = _env.get_template("index.html")
    html = template.render(
        message=message, error=error, query=query, search_results=search_results, documents=documents
    )
    return HTMLResponse(html)


async def ui_index(request: Request) -> HTMLResponse:
    message = request.query_params.get("message")
    error = request.query_params.get("error") == "1"
    return await _render_index(message=message, error=error)


async def ui_create_document(request: Request) -> RedirectResponse:
    form = await request.form()
    title = (form.get("title") or "").strip()
    category = form.get("category") or "other"
    content = (form.get("content") or "").strip()

    if category not in _ALLOWED_CATEGORIES:
        category = "other"

    upload = form.get("content_file")
    if isinstance(upload, UploadFile) and upload.filename:
        if not upload.filename.lower().endswith(".md"):
            return RedirectResponse(
                "/ui?error=1&message=Only+.md+files+are+supported+right+now", status_code=303
            )
        raw = await upload.read()
        try:
            content = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            return RedirectResponse("/ui?error=1&message=File+must+be+UTF-8+text", status_code=303)
        if not title:
            title = Path(upload.filename).stem

    if not title or not content:
        return RedirectResponse(
            f"/ui?error=1&message=Title+and+content+are+both+required", status_code=303
        )

    source_path = f"ui/{category}/{_slugify(title)}-{uuid.uuid4().hex[:8]}.md"
    try:
        embedding = embed_one(f"{title}\n{content}")
        pool = await get_pool()
        await upsert_document(pool, source_path, title, content, embedding)
    except Exception as exc:  # noqa: BLE001
        logger.error("ui_create_document_failed", error=str(exc))
        return RedirectResponse("/ui?error=1&message=Failed+to+index+document", status_code=303)

    logger.info("ui_document_created", source_path=source_path, title=title)
    return RedirectResponse(f"/ui?message=Added+%22{title[:40]}%22", status_code=303)


async def ui_delete_document(request: Request) -> RedirectResponse:
    form = await request.form()
    source_path = form.get("source_path")
    if not source_path:
        return RedirectResponse("/ui?error=1&message=Missing+document+reference", status_code=303)

    pool = await get_pool()
    deleted = await delete_document(pool, source_path)
    if deleted:
        logger.info("ui_document_deleted", source_path=source_path)
        return RedirectResponse("/ui?message=Document+deleted", status_code=303)
    return RedirectResponse("/ui?error=1&message=Document+not+found", status_code=303)


async def ui_search(request: Request) -> HTMLResponse:
    query = request.query_params.get("q", "").strip()
    if not query:
        return await _render_index()

    try:
        query_embedding = embed_one(query)
        pool = await get_pool()
        results = await search(pool, query_embedding, top_k=5)
    except Exception as exc:  # noqa: BLE001
        logger.error("ui_search_failed", error=str(exc))
        return await _render_index(message="Search failed -- see server logs", error=True, query=query)

    return await _render_index(query=query, search_results=results)
