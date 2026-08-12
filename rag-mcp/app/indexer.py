"""Walks knowledge-base/ and (re)indexes every markdown file as one embedding each -- see
docs/adr/0006, D5-D6. Also resolves [[wikilink]]-style references between documents into
rag.document_links -- see docs/adr/0008, D10."""

from __future__ import annotations

import re
from pathlib import Path

import structlog

from app.config import settings
from app.db import ensure_schema, get_pool, replace_links, upsert_document
from app.embeddings import embed_many

logger = structlog.get_logger(__name__)

_SUBDIRS = ("known-issues", "faq", "release-notes")
_MAX_CHARS = 4000  # generous; these files are already short (see knowledge-base/ content)
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def extract_wikilinks(content: str) -> list[str]:
    """Titles referenced via [[Title]] syntax, in order of first appearance, de-duplicated."""
    seen: dict[str, None] = {}
    for match in _WIKILINK_RE.finditer(content):
        title = match.group(1).strip()
        if title:
            seen.setdefault(title, None)
    return list(seen)


def _discover_files() -> list[Path]:
    base = Path(settings.knowledge_base_dir)
    files = []
    for subdir in _SUBDIRS:
        directory = base / subdir
        if directory.is_dir():
            files.extend(sorted(directory.glob("*.md")))
    return files


def _read_document(path: Path) -> tuple[str, str, str]:
    """Returns (source_path, title, content)."""
    text = path.read_text(encoding="utf-8")[:_MAX_CHARS]
    first_line = text.splitlines()[0] if text else path.stem
    title = first_line.lstrip("#").strip() or path.stem
    return str(path.as_posix()), title, text


async def reindex() -> int:
    """(Re)embeds every knowledge-base file and upserts it, then resolves [[wikilinks]] between
    them. Returns the number of documents indexed. Safe to call repeatedly (upsert on
    source_path, not insert-only).

    Link resolution is a second pass over all documents, after every one of them has been
    upserted -- a document's [[wikilinks]] can reference another document indexed later in the
    same run (or file listing order), and resolution is by title lookup against what's already in
    Postgres, so it only works once every title actually exists there. See docs/adr/0008, D10."""
    files = _discover_files()
    if not files:
        logger.warning("no_knowledge_base_files_found", dir=settings.knowledge_base_dir)
        return 0

    documents = [_read_document(f) for f in files]
    embeddings = embed_many([f"{title}\n{content}" for _, title, content in documents])

    pool = await get_pool()
    await ensure_schema(pool)
    for (source_path, title, content), embedding in zip(documents, embeddings):
        await upsert_document(pool, source_path, title, content, embedding)

    for source_path, _title, content in documents:
        wikilinks = extract_wikilinks(content)
        if wikilinks:
            await replace_links(pool, source_path, wikilinks)

    logger.info("reindexed", count=len(documents))
    return len(documents)
