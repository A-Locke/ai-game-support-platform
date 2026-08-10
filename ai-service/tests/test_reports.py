from starlette.testclient import TestClient

from app import main as main_module
from app.main import app

client = TestClient(app)


def test_reports_summary_combines_data_and_claude_summary(monkeypatch):
    async def _fake_fetch(since, until):
        return {"total_conversations": 12, "spam_count": 2, "categories": {"Bug": 5}}

    async def _fake_build(since, until):
        data = await _fake_fetch(since, until)
        return {"data": data, "summary": "Mostly bug reports."}

    monkeypatch.setattr(main_module, "build_report_summary", _fake_build)

    response = client.get("/reports/summary?since=2026-08-01&until=2026-08-10")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Mostly bug reports."
    assert body["data"]["total_conversations"] == 12


def test_reports_summary_raw_skips_claude(monkeypatch):
    called = False

    async def _fake_fetch(since, until):
        nonlocal called
        called = True
        return {"total_conversations": 3}

    monkeypatch.setattr(main_module, "fetch_report_data", _fake_fetch)

    response = client.get("/reports/summary?raw=true")

    assert response.status_code == 200
    assert response.json() == {"data": {"total_conversations": 3}}
    assert called is True
