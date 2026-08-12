from pathlib import Path

from app import indexer
from app.config import settings


def test_discover_files_finds_markdown_under_known_subdirs(tmp_path, monkeypatch):
    (tmp_path / "known-issues").mkdir()
    (tmp_path / "faq").mkdir()
    (tmp_path / "release-notes").mkdir()
    (tmp_path / "sample-tickets").mkdir()  # not indexed -- not a knowledge subdir

    (tmp_path / "known-issues" / "ki-1.md").write_text("# KI-1\ncontent", encoding="utf-8")
    (tmp_path / "faq" / "general.md").write_text("# FAQ\ncontent", encoding="utf-8")
    (tmp_path / "sample-tickets" / "01.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(settings, "knowledge_base_dir", str(tmp_path))

    files = indexer._discover_files()

    names = {f.name for f in files}
    assert names == {"ki-1.md", "general.md"}


def test_discover_files_handles_missing_subdirs_gracefully(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "knowledge_base_dir", str(tmp_path / "does-not-exist"))

    assert indexer._discover_files() == []


def test_read_document_extracts_title_from_first_markdown_heading(tmp_path):
    path = tmp_path / "ki-014.md"
    path.write_text("# KI-014 — Large export crash\n\nSome description.", encoding="utf-8")

    source_path, title, content = indexer._read_document(path)

    assert title == "KI-014 — Large export crash"
    assert "Some description." in content
    assert source_path.endswith("ki-014.md")


def test_read_document_falls_back_to_filename_when_no_heading(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("just some text, no heading", encoding="utf-8")

    _, title, _ = indexer._read_document(path)

    assert title == "just some text, no heading"


async def test_reindex_returns_zero_and_logs_when_no_files_found(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "knowledge_base_dir", str(tmp_path / "empty"))

    count = await indexer.reindex()

    assert count == 0


def test_extract_wikilinks_finds_all_and_dedupes():
    content = "See [[Known Issue A]] and also [[Known Issue B]]. Again: [[Known Issue A]]."

    assert indexer.extract_wikilinks(content) == ["Known Issue A", "Known Issue B"]


def test_extract_wikilinks_returns_empty_list_when_none_present():
    assert indexer.extract_wikilinks("no links here") == []


def test_extract_wikilinks_strips_whitespace_and_skips_empty():
    content = "[[  Padded Title  ]] and [[]]"

    assert indexer.extract_wikilinks(content) == ["Padded Title"]


async def test_reindex_resolves_wikilinks_after_upserting_everything(tmp_path, monkeypatch):
    (tmp_path / "known-issues").mkdir()
    (tmp_path / "known-issues" / "a.md").write_text(
        "# Doc A\n\nSee [[Doc B]] for details.", encoding="utf-8"
    )
    (tmp_path / "known-issues" / "b.md").write_text("# Doc B\n\nNo links here.", encoding="utf-8")
    monkeypatch.setattr(settings, "knowledge_base_dir", str(tmp_path))

    monkeypatch.setattr(indexer, "get_pool", lambda: _async_return("fake-pool"))

    async def _fake_ensure_schema(pool):
        pass

    monkeypatch.setattr(indexer, "ensure_schema", _fake_ensure_schema)

    upserted = []

    async def _fake_upsert(pool, source_path, title, content, embedding):
        upserted.append(source_path)

    monkeypatch.setattr(indexer, "upsert_document", _fake_upsert)
    monkeypatch.setattr(indexer, "embed_many", lambda texts: [[0.1]] * len(texts))

    link_calls = []

    async def _fake_replace_links(pool, source_path, target_titles):
        link_calls.append((source_path, target_titles))
        return []

    monkeypatch.setattr(indexer, "replace_links", _fake_replace_links)

    count = await indexer.reindex()

    assert count == 2
    # Both documents must already be upserted before link resolution runs.
    assert len(upserted) == 2
    assert len(link_calls) == 1
    source_path, target_titles = link_calls[0]
    assert source_path.endswith("a.md")
    assert target_titles == ["Doc B"]


async def _async_return(value):
    return value
