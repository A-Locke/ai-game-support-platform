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
