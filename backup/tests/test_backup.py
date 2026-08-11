import datetime

from app import backup
from app.config import settings
from app.pg import PgError


def test_skips_when_s3_not_configured(monkeypatch):
    settings.s3_bucket = ""
    called = False

    def _fake_dump(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(backup, "dump_to_file", _fake_dump)

    result = backup.run()

    assert result == 0
    assert called is False


def test_uploads_dump_to_s3(monkeypatch, s3_bucket, tmp_path):
    def _fake_dump(*, out_path, **kwargs):
        with open(out_path, "wb") as f:
            f.write(b"fake dump content")

    monkeypatch.setattr(backup, "dump_to_file", _fake_dump)
    monkeypatch.setattr(backup, "get_client", lambda: s3_bucket)

    result = backup.run()

    assert result == 0
    objects = s3_bucket.list_objects_v2(Bucket="test-backups-bucket").get("Contents", [])
    assert len(objects) == 1
    assert objects[0]["Key"].startswith("chatwoot-backups/chatwoot-")
    assert objects[0]["Key"].endswith(".dump")


def test_pg_dump_failure_propagates(monkeypatch, s3_bucket):
    def _fake_dump(**kwargs):
        raise PgError("pg_dump failed (exit 1): connection refused")

    monkeypatch.setattr(backup, "dump_to_file", _fake_dump)
    monkeypatch.setattr(backup, "get_client", lambda: s3_bucket)

    try:
        backup.run()
        assert False, "expected PgError to propagate"
    except PgError:
        pass

    # A failed dump must never produce a (misleadingly empty/partial) uploaded backup.
    objects = s3_bucket.list_objects_v2(Bucket="test-backups-bucket").get("Contents", [])
    assert objects == []


def test_prune_old_backups_deletes_only_objects_past_retention(monkeypatch):
    now = datetime.datetime.now(datetime.timezone.utc)
    old = {"Key": "chatwoot-backups/chatwoot-old.dump", "LastModified": now - datetime.timedelta(days=30)}
    recent = {"Key": "chatwoot-backups/chatwoot-recent.dump", "LastModified": now - datetime.timedelta(days=1)}

    monkeypatch.setattr(backup, "list_backups", lambda client: [old, recent])

    deleted = {}

    class FakeClient:
        def delete_objects(self, Bucket, Delete):
            deleted["bucket"] = Bucket
            deleted["keys"] = [o["Key"] for o in Delete["Objects"]]

    settings.backup_retention_days = 14
    backup._prune_old_backups(FakeClient())

    assert deleted["keys"] == [old["Key"]]


def test_prune_disabled_when_retention_is_zero(monkeypatch):
    settings.backup_retention_days = 0
    monkeypatch.setattr(backup, "list_backups", lambda client: (_ for _ in ()).throw(AssertionError("should not be called")))

    backup._prune_old_backups(client=None)  # must return before ever touching list_backups
