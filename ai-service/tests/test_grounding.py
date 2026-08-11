from app import grounding
from app.config import settings


async def test_search_related_issues_returns_empty_when_nothing_configured():
    settings.jira_mcp_url = ""
    settings.azure_devops_mcp_url = ""

    result = await grounding.search_related_issues("crash on export")

    assert result == ""


async def test_search_jira_skipped_when_url_unset(monkeypatch):
    settings.jira_mcp_url = ""
    called = False

    async def _fake_call(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(grounding, "_call", _fake_call)

    result = await grounding._search_jira("x")

    assert result == []
    assert called is False


async def test_search_jira_failure_degrades_to_empty_list(monkeypatch):
    settings.jira_mcp_url = "http://jira-mcp.test/mcp"

    async def _raise(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(grounding, "_call", _raise)

    result = await grounding._search_jira("crash on export")

    assert result == []


async def test_search_azure_devops_failure_degrades_to_empty_list(monkeypatch):
    settings.azure_devops_mcp_url = "http://ado-mcp.test/mcp"

    async def _raise(*args, **kwargs):
        raise RuntimeError("unauthorized")

    monkeypatch.setattr(grounding, "_call", _raise)

    result = await grounding._search_azure_devops("crash on export")

    assert result == []


def test_normalize_jira_extracts_key_summary_status():
    raw = {
        "issues": [
            {"key": "SUP-42", "fields": {"summary": "Export crashes over 10k rows", "status": {"name": "Open"}}},
        ]
    }

    result = grounding._normalize_jira(raw)

    assert result == [{"source": "jira", "id": "SUP-42", "summary": "Export crashes over 10k rows", "status": "Open"}]


def test_normalize_jira_skips_entries_missing_required_fields():
    raw = {"issues": [{"key": "SUP-1"}, {"fields": {"summary": "no key"}}, "not-a-dict"]}

    result = grounding._normalize_jira(raw)

    assert result == []


def test_normalize_jira_handles_none_and_unexpected_shapes():
    assert grounding._normalize_jira(None) == []
    assert grounding._normalize_jira({"unexpected": "shape"}) == []
    assert grounding._normalize_jira("not even a dict") == []


def test_normalize_ado_extracts_id_title_state():
    raw = {"results": [{"id": 123, "fields": {"System.Title": "Crash on export", "System.State": "Active"}}]}

    result = grounding._normalize_ado(raw)

    assert result == [{"source": "azure_devops", "id": "123", "summary": "Crash on export", "status": "Active"}]


def test_normalize_ado_tries_alternate_shape_keys():
    raw = {"workItems": [{"id": 5, "fields": {"System.Title": "X", "System.State": "New"}}]}
    assert len(grounding._normalize_ado(raw)) == 1

    raw2 = [{"id": 6, "fields": {"System.Title": "Y", "System.State": "New"}}]
    assert len(grounding._normalize_ado(raw2)) == 1


async def test_search_related_issues_combines_and_formats_both_sources(monkeypatch):
    settings.jira_mcp_url = "http://jira-mcp.test/mcp"
    settings.azure_devops_mcp_url = "http://ado-mcp.test/mcp"

    async def _fake_jira(query):
        return [{"source": "jira", "id": "SUP-1", "summary": "Export crash", "status": "Open"}]

    async def _fake_ado(query):
        return [{"source": "azure_devops", "id": "99", "summary": "Timeout on export", "status": "Active"}]

    monkeypatch.setattr(grounding, "_search_jira", _fake_jira)
    monkeypatch.setattr(grounding, "_search_azure_devops", _fake_ado)

    result = await grounding.search_related_issues("export crash")

    assert "SUP-1" in result
    assert "99" in result
    assert "Export crash" in result
    assert "Timeout on export" in result
