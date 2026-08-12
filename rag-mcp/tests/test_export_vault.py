import zipfile
from io import BytesIO

from app import export_vault


def test_safe_filename_strips_invalid_characters():
    assert export_vault.safe_filename('Known Issue: "Export" fails <badly>') == "Known Issue- -Export- fails -badly-"


def test_safe_filename_falls_back_to_untitled_when_empty():
    assert export_vault.safe_filename("   ") == "untitled"


def test_safe_filename_truncates_long_titles():
    long_title = "A" * 300
    assert len(export_vault.safe_filename(long_title)) == 120


async def test_export_vault_writes_one_file_per_document(tmp_path, monkeypatch):
    monkeypatch.setattr(export_vault, "get_pool", lambda: _async_return("pool"))

    async def _fake_list(pool):
        return [
            {"source_path": "a.md", "title": "Doc A", "content": "Body A, links to [[Doc B]]."},
            {"source_path": "b.md", "title": "Doc B", "content": "Body B."},
        ]

    monkeypatch.setattr(export_vault, "list_documents", _fake_list)

    written = await export_vault.export_vault(tmp_path)

    assert written == 2
    assert (tmp_path / "Doc A.md").read_text(encoding="utf-8") == "Body A, links to [[Doc B]]."
    assert (tmp_path / "Doc B.md").read_text(encoding="utf-8") == "Body B."


async def test_export_vault_disambiguates_duplicate_titles(tmp_path, monkeypatch):
    monkeypatch.setattr(export_vault, "get_pool", lambda: _async_return("pool"))

    async def _fake_list(pool):
        return [
            {"source_path": "a.md", "title": "Same Title", "content": "First."},
            {"source_path": "b.md", "title": "Same Title", "content": "Second."},
        ]

    monkeypatch.setattr(export_vault, "list_documents", _fake_list)

    written = await export_vault.export_vault(tmp_path)

    assert written == 2
    assert (tmp_path / "Same Title.md").read_text(encoding="utf-8") == "First."
    assert (tmp_path / "Same Title-1.md").read_text(encoding="utf-8") == "Second."


async def test_build_vault_zip_contains_one_entry_per_document(monkeypatch):
    async def _fake_list(pool):
        return [
            {"source_path": "a.md", "title": "Doc A", "content": "Body A, links to [[Doc B]]."},
            {"source_path": "b.md", "title": "Doc B", "content": "Body B."},
        ]

    monkeypatch.setattr(export_vault, "list_documents", _fake_list)

    zip_bytes = await export_vault.build_vault_zip("fake-pool")

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert names == {"Doc A.md", "Doc B.md"}
        assert zf.read("Doc A.md").decode("utf-8") == "Body A, links to [[Doc B]]."
        assert zf.read("Doc B.md").decode("utf-8") == "Body B."


async def test_build_vault_zip_disambiguates_duplicate_titles(monkeypatch):
    async def _fake_list(pool):
        return [
            {"source_path": "a.md", "title": "Same Title", "content": "First."},
            {"source_path": "b.md", "title": "Same Title", "content": "Second."},
        ]

    monkeypatch.setattr(export_vault, "list_documents", _fake_list)

    zip_bytes = await export_vault.build_vault_zip("fake-pool")

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        assert set(zf.namelist()) == {"Same Title.md", "Same Title-1.md"}


async def test_build_vault_zip_empty_when_no_documents(monkeypatch):
    monkeypatch.setattr(export_vault, "list_documents", lambda pool: _async_return([]))

    zip_bytes = await export_vault.build_vault_zip("fake-pool")

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        assert zf.namelist() == []


async def _async_return(value):
    return value
