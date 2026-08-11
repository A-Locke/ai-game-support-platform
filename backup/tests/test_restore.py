import datetime

import pytest

from app import restore
from app.config import settings


def test_run_requires_s3_bucket_configured():
    settings.s3_bucket = ""
    with pytest.raises(SystemExit):
        restore.run()


def test_resolve_key_uses_most_recent_when_not_specified(monkeypatch):
    now = datetime.datetime.now(datetime.timezone.utc)
    older = {"Key": "chatwoot-backups/chatwoot-older.dump", "LastModified": now - datetime.timedelta(days=2)}
    newer = {"Key": "chatwoot-backups/chatwoot-newer.dump", "LastModified": now - datetime.timedelta(days=1)}
    monkeypatch.setattr(restore, "list_backups", lambda client: [older, newer])

    key = restore.resolve_key(client=None, explicit_key=None)

    assert key == newer["Key"]


def test_resolve_key_uses_explicit_key_without_listing(monkeypatch):
    monkeypatch.setattr(
        restore, "list_backups", lambda client: (_ for _ in ()).throw(AssertionError("should not list"))
    )

    key = restore.resolve_key(client=None, explicit_key="chatwoot-backups/chatwoot-specific.dump")

    assert key == "chatwoot-backups/chatwoot-specific.dump"


def test_resolve_key_raises_when_no_backups_exist(monkeypatch):
    monkeypatch.setattr(restore, "list_backups", lambda client: [])

    with pytest.raises(SystemExit):
        restore.resolve_key(client=None, explicit_key=None)


def test_confirmation_prompt_abort_skips_restore(monkeypatch):
    monkeypatch.setattr(restore, "get_client", lambda: object())
    monkeypatch.setattr(restore, "resolve_key", lambda client, key: "chatwoot-backups/chatwoot-x.dump")
    called = False

    def _fake_restore(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(restore, "restore_from_file", _fake_restore)

    result = restore.run(confirm=lambda prompt: "no")

    assert result == 1
    assert called is False


def test_yes_flag_skips_confirmation_prompt(monkeypatch, tmp_path):
    class FakeClient:
        def download_file(self, bucket, key, path):
            with open(path, "wb") as f:
                f.write(b"fake dump")

    monkeypatch.setattr(restore, "get_client", lambda: FakeClient())
    monkeypatch.setattr(restore, "resolve_key", lambda client, key: "chatwoot-backups/chatwoot-x.dump")

    restored = {}

    def _fake_restore(**kwargs):
        restored.update(kwargs)

    monkeypatch.setattr(restore, "restore_from_file", _fake_restore)

    def _confirm_should_not_be_called(prompt):
        raise AssertionError("confirmation prompt should be skipped with --yes")

    result = restore.run(yes=True, confirm=_confirm_should_not_be_called)

    assert result == 0
    assert restored["database"] == settings.postgres_database
