"""Loads a short excerpt of the knowledge base (known issues + FAQ) to ground Claude's
classification/draft in real product context. Deliberately short -- see docs/ai-workflows.md's
note on keeping the classification prompt small."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.config import settings

_MAX_CHARS_PER_FILE = 1500


def _read_markdown_files(directory: Path) -> str:
    if not directory.is_dir():
        return ""
    chunks = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")[:_MAX_CHARS_PER_FILE]
        chunks.append(f"### {path.stem}\n{text}")
    return "\n\n".join(chunks)


@lru_cache
def load_knowledge_excerpt() -> str:
    base = Path(settings.knowledge_base_dir)
    known_issues = _read_markdown_files(base / "known-issues")
    faq = _read_markdown_files(base / "faq")
    sections = [s for s in (known_issues, faq) if s]
    return "\n\n".join(sections) if sections else "(no knowledge base found)"
