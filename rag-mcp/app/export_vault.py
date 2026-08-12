"""Exports the current knowledge base as an Obsidian-compatible vault -- a folder of real .md
files, one per document, named after its title. Since document content already contains whatever
literal [[wikilinks]] were typed or resolved into it (docs/adr/0008, D10), Obsidian's own linking
engine builds the same graph rag.document_links represents, with no extra data needed here. A
read-only snapshot for browsing the graph view natively in Obsidian, not infrastructure the
running platform depends on -- see docs/adr/0008, D11.

Two ways to get it: the /ui/vault-download button (zipped in memory, no shell/SSH access to the
server needed -- see app/ui.py) or, for whoever's already operating the server:
    docker compose exec rag-mcp python -m app.export_vault
    docker compose cp rag-mcp:/app/export ./obsidian-vault-export
"""

from __future__ import annotations

import asyncio
import io
import re
import sys
import zipfile
from pathlib import Path

from app.db import get_pool, list_documents

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')
_DEFAULT_OUTPUT_DIR = Path("/app/export")


def safe_filename(title: str) -> str:
    """A title made safe as a filename on Windows/Mac/Linux alike -- Obsidian resolves
    [[Title]] links by filename, so this has to match how titles are typed in wikilinks."""
    name = _INVALID_FILENAME_CHARS.sub("-", title).strip()
    return (name or "untitled")[:120]


async def _vault_files(pool) -> list[tuple[str, str]]:
    """(filename, content) pairs for every indexed document, titles disambiguated with a numeric
    suffix on collision -- shared by both the on-disk export and the in-memory zip below so
    there's exactly one place that decides how a title becomes a filename."""
    documents = await list_documents(pool)
    seen_names: dict[str, int] = {}
    files: list[tuple[str, str]] = []
    for doc in documents:
        base_name = safe_filename(doc["title"])
        count = seen_names.get(base_name, 0)
        seen_names[base_name] = count + 1
        filename = f"{base_name}.md" if count == 0 else f"{base_name}-{count}.md"
        files.append((filename, doc["content"]))
    return files


async def export_vault(output_dir: Path) -> int:
    """Writes one .md file per indexed document into output_dir. Returns the number written."""
    output_dir.mkdir(parents=True, exist_ok=True)
    pool = await get_pool()
    files = await _vault_files(pool)
    for filename, content in files:
        (output_dir / filename).write_text(content, encoding="utf-8")
    return len(files)


async def build_vault_zip(pool) -> bytes:
    """The same vault export_vault() would write to disk, zipped in memory instead -- backs the
    /ui/vault-download button so QA/CS staff can get it without shell/SSH access to the server."""
    files = await _vault_files(pool)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files:
            zf.writestr(filename, content)
    return buffer.getvalue()


def main() -> None:
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_OUTPUT_DIR
    written = asyncio.run(export_vault(output_dir))
    print(f"Exported {written} document(s) to {output_dir}")


if __name__ == "__main__":
    main()
