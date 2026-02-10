# Copyright 2026 Piotr Synak
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Purpose:
# Unit tests for lightweight migration/ingestion utilities.

from __future__ import annotations

from pathlib import Path

from scripts.ensure_ingested import _compute_knowledge_hash
from scripts.run_migrations import _split_sql_statements


def test_split_sql_statements_handles_basic_semicolons() -> None:
    sql = "CREATE TABLE t(a int);\nALTER TABLE t ADD COLUMN b text;\n"
    parts = _split_sql_statements(sql)
    assert parts == ["CREATE TABLE t(a int)", "ALTER TABLE t ADD COLUMN b text"]


def test_split_sql_statements_ignores_semicolons_in_dollar_quoted_blocks() -> None:
    sql = """
    DO $$
    BEGIN
      PERFORM 1;
    END;
    $$;

    ALTER TABLE t ADD COLUMN c text;
    """
    parts = _split_sql_statements(sql)
    # We expect the DO block and the ALTER to be separate statements.
    assert len(parts) == 2
    assert parts[0].lstrip().startswith("DO $$")
    assert parts[1].strip() == "ALTER TABLE t ADD COLUMN c text"


def test_compute_knowledge_hash_changes_when_content_changes(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    root.mkdir()
    p = root / "cards" / "a.md"
    p.parent.mkdir()
    p.write_text("hello", encoding="utf-8")

    h1 = _compute_knowledge_hash(root)
    p.write_text("hello world", encoding="utf-8")
    h2 = _compute_knowledge_hash(root)

    assert h1 != h2
