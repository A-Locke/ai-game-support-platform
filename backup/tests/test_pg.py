import subprocess

import pytest

from app import pg


def test_dump_to_file_raises_on_nonzero_exit(monkeypatch):
    def _fake_run(cmd, env, capture_output, text):
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="connection refused")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(pg.PgError, match="connection refused"):
        pg.dump_to_file(host="h", port="5432", username="u", password="p", database="d", out_path="/tmp/x")


def test_dump_to_file_passes_custom_format_flag(monkeypatch):
    captured = {}

    def _fake_run(cmd, env, capture_output, text):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    pg.dump_to_file(host="h", port="5432", username="u", password="p", database="d", out_path="/tmp/x")

    assert "-Fc" in captured["cmd"]
    assert captured["cmd"][-1] == "d"


def test_restore_from_file_passes_clean_if_exists_flags(monkeypatch):
    captured = {}

    def _fake_run(cmd, env, capture_output, text):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    pg.restore_from_file(host="h", port="5432", username="u", password="p", database="d", in_path="/tmp/x.dump")

    assert "--clean" in captured["cmd"]
    assert "--if-exists" in captured["cmd"]


def test_restore_from_file_raises_on_nonzero_exit(monkeypatch):
    def _fake_run(cmd, env, capture_output, text):
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="fatal error")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(pg.PgError, match="fatal error"):
        pg.restore_from_file(host="h", port="5432", username="u", password="p", database="d", in_path="/tmp/x.dump")
