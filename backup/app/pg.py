"""Thin subprocess wrappers around pg_dump/pg_restore -- no SQL parsing, no ORM, just the same
binaries a human would run by hand. See docs/adr/0002, D1-D2."""

from __future__ import annotations

import os
import subprocess


class PgError(Exception):
    pass


def _pg_env(password: str) -> dict:
    return {**os.environ, "PGPASSWORD": password}


def dump_to_file(*, host: str, port: str, username: str, password: str, database: str, out_path: str) -> None:
    cmd = ["pg_dump", "-h", host, "-p", str(port), "-U", username, "-Fc", "-f", out_path, database]
    result = subprocess.run(cmd, env=_pg_env(password), capture_output=True, text=True)
    if result.returncode != 0:
        raise PgError(f"pg_dump failed (exit {result.returncode}): {result.stderr.strip()}")


def restore_from_file(*, host: str, port: str, username: str, password: str, database: str, in_path: str) -> None:
    # --if-exists matters specifically for restoring into a fresh/empty database: without it,
    # --clean's DROP statements for objects that don't exist yet are reported as errors (not
    # fatal, but they change pg_restore's exit code) -- see docs/adr/0002, D1.
    cmd = [
        "pg_restore",
        "-h", host,
        "-p", str(port),
        "-U", username,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "-d", database,
        in_path,
    ]
    result = subprocess.run(cmd, env=_pg_env(password), capture_output=True, text=True)
    if result.returncode != 0:
        raise PgError(f"pg_restore failed (exit {result.returncode}): {result.stderr.strip()}")
