# Copyright 2026 Piotr Synak
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Purpose:
# Unit tests for the retrieval post-processing logic (no DB / no embeddings service).

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import retrieval


class _Cursor:
    def __init__(self, rows: list[tuple]):
        self._rows = rows
        self.executed: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *args, **kwargs):
        self.executed.append((args, kwargs))
        return None

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, rows: list[tuple]):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _Cursor(self._rows)


def _settings(**overrides):
    base = SimpleNamespace(
        database_url="postgresql://test:test@localhost:5432/test",
        embeddings_provider="stub",
        embeddings_dimensions=3,
        retrieval_max_distance=None,
        retrieval_distance_delta=None,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_retrieve_returns_empty_when_db_returns_no_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retrieval, "get_settings", lambda: _settings())
    monkeypatch.setattr(retrieval, "register_vector", lambda conn: None)
    monkeypatch.setattr(retrieval.psycopg, "connect", lambda *a, **k: _Conn([]))

    class _Provider:
        def embed(self, texts: list[str]):
            return [[0.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(retrieval, "get_embedding_provider", lambda **k: _Provider())
    assert retrieval.retrieve("q") == []


def test_retrieve_includes_conversation_topic_in_embedding_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retrieval, "get_settings", lambda: _settings())
    monkeypatch.setattr(retrieval, "register_vector", lambda conn: None)
    monkeypatch.setattr(
        retrieval.psycopg,
        "connect",
        lambda *a, **k: _Conn(
            [
                (
                    "c1",
                    "cat",
                    "Overview",
                    None,
                    "text.",
                    0.1,
                )
            ]
        ),
    )

    captured: dict[str, object] = {}

    class _Provider:
        def embed(self, texts: list[str]):
            captured["texts"] = texts
            return [[0.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(retrieval, "get_embedding_provider", lambda **k: _Provider())
    retrieval.retrieve("What?", conversation_topic="topic")
    assert captured["texts"] == ["What?\n\nConversation topic: topic"]


def test_retrieve_postprocesses_sections_and_diversifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Configure cutoffs to filter one row via max_distance and one via delta.
    monkeypatch.setattr(
        retrieval,
        "get_settings",
        lambda: _settings(retrieval_max_distance=0.50, retrieval_distance_delta=0.20),
    )
    monkeypatch.setattr(retrieval, "register_vector", lambda conn: None)

    # Mix of low-signal and substantive sections.
    # Row tuple: (card_id, category, section, source_url, content, distance)
    rows = [
        ("cardA", "x", "Title", None, "short", 0.10),
        ("cardA", "x", "What I built", None, "Long. " * 200, 0.12),
        ("cardA", "x", "My role", None, "tiny.", 0.13),
        ("cardA", "x", "Tech stack", None, "python", 0.14),
        ("cardB", "y", "Title", None, "hdr", 0.11),
        ("cardB", "y", "Overview", None, "This is substantive. " * 30, 0.15),
        # Should be filtered by max_distance.
        ("cardC", "z", "Overview", None, "far", 0.99),
        # Should be filtered by delta (best=0.10, delta=0.20 => threshold=0.30).
        ("cardD", "z", "Overview", None, "also far", 0.60),
    ]

    monkeypatch.setattr(retrieval.psycopg, "connect", lambda *a, **k: _Conn(rows))

    class _Provider:
        def embed(self, texts: list[str]):
            return [[0.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(retrieval, "get_embedding_provider", lambda **k: _Provider())

    # Ask for more than per-card cap to force the "fill remaining slots without cap" path.
    chunks = retrieval.retrieve("q", limit=4)
    assert 1 <= len(chunks) <= 4

    # Ensure we didn't return only low-signal sections when substantive exists.
    sections = {c.section.lower() for c in chunks}
    assert "what i built" in sections or "overview" in sections
