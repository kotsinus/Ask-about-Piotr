# Copyright 2026 Piotr Synak
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Purpose:
# Applies SQL migration files from backend/db/migrations to an existing Postgres DB.
#
# Notes:
# - Designed to be safe to run at container start (idempotent migrations).
# - Does NOT replace a full migration framework; it's a lightweight bootstrap.

from __future__ import annotations

import argparse
import hashlib
import os
import time
from pathlib import Path

import psycopg

MIGRATIONS_LOCK_ID = 684321001  # arbitrary constant


def _wait_for_db(database_url: str, *, timeout_s: float = 60.0) -> None:
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with psycopg.connect(database_url):
                return
        except Exception as exc:
            last_error = exc
            time.sleep(1.0)
    raise RuntimeError(f"Database not reachable within {timeout_s}s") from last_error


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split_sql_statements(sql_text: str) -> list[str]:
    """Split SQL into statements while respecting strings/comments/dollar quotes.

    This intentionally supports common Postgres DDL, but avoids being a full SQL parser.
    """

    statements: list[str] = []
    buf: list[str] = []

    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    dollar_tag: str | None = None

    i = 0
    n = len(sql_text)

    def _flush() -> None:
        stmt = "".join(buf).strip()
        buf.clear()
        if stmt:
            statements.append(stmt)

    while i < n:
        ch = sql_text[i]
        nxt = sql_text[i + 1] if i + 1 < n else ""

        # Handle line comments.
        if in_line_comment:
            buf.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        # Handle block comments.
        if in_block_comment:
            buf.append(ch)
            if ch == "*" and nxt == "/":
                buf.append(nxt)
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        # Start of comment (only when not inside quotes).
        if not in_single and not in_double and dollar_tag is None:
            if ch == "-" and nxt == "-":
                buf.append(ch)
                buf.append(nxt)
                in_line_comment = True
                i += 2
                continue
            if ch == "/" and nxt == "*":
                buf.append(ch)
                buf.append(nxt)
                in_block_comment = True
                i += 2
                continue

        # Dollar-quoted blocks.
        if not in_single and not in_double:
            if dollar_tag is None and ch == "$":
                # Try to parse $tag$ or $$.
                j = i + 1
                while j < n and sql_text[j] != "$" and sql_text[j] != "\n":
                    j += 1
                if j < n and sql_text[j] == "$":
                    tag = sql_text[i : j + 1]
                    # Accept $$ or $name$ style.
                    if tag == "$$" or (
                        len(tag) >= 3
                        and tag[1:-1].replace("_", "a").isalnum()
                    ):
                        dollar_tag = tag
                        buf.append(tag)
                        i = j + 1
                        continue
            elif dollar_tag is not None and sql_text.startswith(dollar_tag, i):
                buf.append(dollar_tag)
                i += len(dollar_tag)
                dollar_tag = None
                continue

        # Quotes.
        if dollar_tag is None and not in_double and ch == "'":
            # SQL escaping: doubled single-quote inside strings.
            if in_single and nxt == "'":
                buf.append(ch)
                buf.append(nxt)
                i += 2
                continue
            in_single = not in_single
            buf.append(ch)
            i += 1
            continue

        if dollar_tag is None and not in_single and ch == '"':
            in_double = not in_double
            buf.append(ch)
            i += 1
            continue

        # Statement delimiter.
        if not in_single and not in_double and dollar_tag is None and ch == ";":
            _flush()
            i += 1
            continue

        buf.append(ch)
        i += 1

    _flush()
    return statements


def _ensure_schema_migrations_table(conn: psycopg.Connection) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                checksum_sha256 TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
    conn.commit()


def _get_applied(conn: psycopg.Connection) -> dict[str, str]:
    with conn.cursor() as cursor:
        cursor.execute("SELECT filename, checksum_sha256 FROM schema_migrations;")
        return {str(row[0]): str(row[1]) for row in cursor.fetchall()}


def _apply_one(
    conn: psycopg.Connection, *, filename: str, sql_text: str, checksum: str
) -> None:
    statements = _split_sql_statements(sql_text)
    if not statements:
        return

    with conn.transaction():
        with conn.cursor() as cursor:
            for stmt in statements:
                cursor.execute(stmt)
            cursor.execute(
                """
                INSERT INTO schema_migrations (filename, checksum_sha256)
                VALUES (%s, %s);
                """,
                (filename, checksum),
            )


def run_status(database_url: str) -> None:
    _wait_for_db(database_url)
    script_dir = Path(__file__).resolve().parent
    migrations_dir = script_dir.parent / "db" / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql")) if migrations_dir.exists() else []

    with psycopg.connect(database_url) as conn:
        _ensure_schema_migrations_table(conn)
        applied = _get_applied(conn)

    print("Migration status:", flush=True)
    for path in migration_files:
        sql_text = path.read_text(encoding="utf-8")
        checksum = _sha256_text(sql_text)
        if path.name in applied:
            marker = "APPLIED" if applied[path.name] == checksum else "CHECKSUM_MISMATCH"
        else:
            marker = "PENDING"
        print(f"- {path.name}: {marker}", flush=True)


def run_up(database_url: str) -> None:
    _wait_for_db(database_url)
    script_dir = Path(__file__).resolve().parent
    migrations_dir = script_dir.parent / "db" / "migrations"
    if not migrations_dir.exists():
        print(f"No migrations directory found at {migrations_dir}. Skipping.", flush=True)
        return

    migration_files = sorted(migrations_dir.glob("*.sql"))
    if not migration_files:
        print(f"No migration files in {migrations_dir}. Skipping.", flush=True)
        return

    with psycopg.connect(database_url) as conn:
        _ensure_schema_migrations_table(conn)

        # Single-runner safety.
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s);", (MIGRATIONS_LOCK_ID,))

        applied = _get_applied(conn)
        pending: list[Path] = []
        for path in migration_files:
            sql_text = path.read_text(encoding="utf-8")
            checksum = _sha256_text(sql_text)
            if path.name in applied:
                if applied[path.name] != checksum:
                    raise RuntimeError(
                        f"Migration checksum mismatch for {path.name}. "
                        "Refusing to proceed."
                    )
                continue
            pending.append(path)

        print(
            f"Migrations: {len(migration_files)} total, {len(pending)} pending",
            flush=True,
        )

        for path in pending:
            sql_text = path.read_text(encoding="utf-8")
            checksum = _sha256_text(sql_text)
            print(f"Applying {path.name}...", flush=True)
            _apply_one(conn, filename=path.name, sql_text=sql_text, checksum=checksum)

        # Always release lock.
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s);", (MIGRATIONS_LOCK_ID,))

    print("Migrations applied.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        nargs="?",
        default="up",
        choices=("up", "status"),
        help="Migration command",
    )
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to run migrations.")

    if args.command == "status":
        run_status(database_url)
        return
    run_up(database_url)


if __name__ == "__main__":
    main()

