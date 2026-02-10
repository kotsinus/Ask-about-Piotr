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
from app.schemas import Category


class _Cursor:
    def __init__(self, rows: list[tuple]):
        self._rows = rows
        self.executed: list[tuple] = []
        self._filtered_rows: list[tuple] | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *args, **kwargs):
        self.executed.append((args, kwargs))

        # Very small SQL-aware behavior:
        # retrieval.retrieve_for_category adds "category = %s" and passes the
        # category string as a param. Filter rows accordingly so tests can assert
        # per-category semantics.
        if args:
            query = str(args[0])
            params = args[1] if len(args) > 1 else None
            if "category = %s" in query and params:
                # params = (*dynamic_params, candidate_limit)
                # dynamic params start with embedding vector, then category.
                try:
                    category = params[1]
                except Exception:
                    category = None
                if category:
                    self._filtered_rows = [r for r in self._rows if r[2] == category]
        return None

    def fetchall(self):
        return self._filtered_rows if self._filtered_rows is not None else self._rows


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
        retrieval_per_card_cap=2,
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
                    1,
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
    # Row tuple: (id, card_id, category, section, source_url, content, distance)
    rows = [
        (1, "cardA", "x", "Title", None, "short", 0.10),
        (2, "cardA", "x", "What I built", None, "Long. " * 200, 0.12),
        (3, "cardA", "x", "My role", None, "tiny.", 0.13),
        (4, "cardA", "x", "Tech stack", None, "python", 0.14),
        (5, "cardB", "y", "Title", None, "hdr", 0.11),
        (6, "cardB", "y", "Overview", None, "This is substantive. " * 30, 0.15),
        # Should be filtered by max_distance.
        (7, "cardC", "z", "Overview", None, "far", 0.99),
        # Should be filtered by delta (best=0.10, delta=0.20 => threshold=0.30).
        (8, "cardD", "z", "Overview", None, "also far", 0.60),
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


def test_retrieve_for_category_respects_budget_and_per_card_cap_per_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Per-category retrieval should enforce per-card cap within the run.
    monkeypatch.setattr(retrieval, "get_settings", lambda: _settings(retrieval_per_card_cap=1))
    monkeypatch.setattr(retrieval, "register_vector", lambda conn: None)

    # Rows: (id, card_id, category, section, source_url, content, distance)
    rows = [
        (1, "eduA", Category.education_and_formal_background.value, "Overview", None, "x" * 300, 0.10),
        (2, "eduA", Category.education_and_formal_background.value, "Facts", None, "y" * 300, 0.11),
        (3, "eduB", Category.education_and_formal_background.value, "Overview", None, "z" * 300, 0.12),
        (4, "engA", Category.hands_on_engineering.value, "What I built", None, "w" * 300, 0.13),
        (5, "engA", Category.hands_on_engineering.value, "Overview", None, "v" * 300, 0.14),
        (6, "engB", Category.hands_on_engineering.value, "Overview", None, "u" * 300, 0.15),
    ]

    monkeypatch.setattr(retrieval.psycopg, "connect", lambda *a, **k: _Conn(rows))

    class _Provider:
        def embed(self, texts: list[str]):
            return [[0.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(retrieval, "get_embedding_provider", lambda **k: _Provider())

    edu = retrieval.retrieve_for_category(
        "q",
        Category.education_and_formal_background,
        budget=2,
    )
    assert len(edu) <= 2
    assert len({c.card_id for c in edu}) == len(edu), "per-card cap=1 must hold within category"

    eng = retrieval.retrieve_for_category(
        "q",
        Category.hands_on_engineering,
        budget=2,
    )
    assert len(eng) <= 2
    assert len({c.card_id for c in eng}) == len(eng), "per-card cap=1 must hold within category"

    # The cap should be applied per-category: it's okay if both runs include engA/eduA once.
    assert any(c.card_id == "eduA" for c in edu)
    assert any(c.card_id == "engA" for c in eng)


def test_category_section_weighting_affects_ordering_deterministically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retrieval, "get_settings", lambda: _settings(retrieval_per_card_cap=3))
    monkeypatch.setattr(retrieval, "register_vector", lambda conn: None)

    # Same card, close distances; education should prefer "Facts" over "Overview".
    rows = [
        (10, "education-facts", Category.education_and_formal_background.value, "Overview", None, "A" * 300, 0.20),
        (11, "education-facts", Category.education_and_formal_background.value, "Facts", None, "B" * 300, 0.205),
    ]
    monkeypatch.setattr(retrieval.psycopg, "connect", lambda *a, **k: _Conn(rows))

    class _Provider:
        def embed(self, texts: list[str]):
            return [[0.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(retrieval, "get_embedding_provider", lambda **k: _Provider())

    chunks = retrieval.retrieve_for_category(
        "q",
        Category.education_and_formal_background,
        budget=2,
    )
    assert [c.section for c in chunks] == ["Facts", "Overview"]


def test_merge_dedup_and_cap_coverage_invariants_under_cap() -> None:
    # If coverage is impossible (cap < number of required categories), it should be disabled.
    per_category = {
        Category.education_and_formal_background.value: [
            retrieval.RetrievedChunk(
                chunk_id=1,
                card_id="edu",
                category=Category.education_and_formal_background.value,
                section="Facts",
                content="edu fact",
                distance=0.10,
                adjusted_distance=0.10,
                best_origin_category=Category.education_and_formal_background.value,
            )
        ],
        Category.hands_on_engineering.value: [
            retrieval.RetrievedChunk(
                chunk_id=2,
                card_id="eng",
                category=Category.hands_on_engineering.value,
                section="What I built",
                content="eng fact",
                distance=0.11,
                adjusted_distance=0.11,
                best_origin_category=Category.hands_on_engineering.value,
            )
        ],
    }

    out_cap1 = retrieval.merge_dedup_and_cap(
        question="q",
        per_category_selected=per_category,
        routed_categories=[
            Category.education_and_formal_background,
            Category.hands_on_engineering,
        ],
        max_total_chunks=1,
    )
    assert len(out_cap1) == 1

    out_cap2 = retrieval.merge_dedup_and_cap(
        question="q",
        per_category_selected=per_category,
        routed_categories=[
            Category.education_and_formal_background,
            Category.hands_on_engineering,
        ],
        max_total_chunks=2,
    )
    cats = {c.best_origin_category for c in out_cap2}
    assert Category.education_and_formal_background.value in cats
    assert Category.hands_on_engineering.value in cats


def test_metaish_penalty_pushes_policy_like_chunks_down(monkeypatch: pytest.MonkeyPatch) -> None:
    # Meta-ish chunk should receive a soft penalty and rank below a similar-distance factual chunk.
    monkeypatch.setattr(retrieval, "get_settings", lambda: _settings(retrieval_per_card_cap=3))
    monkeypatch.setattr(retrieval, "register_vector", lambda conn: None)

    rows = [
        (
            10,
            "cardA",
            Category.hands_on_engineering.value,
            "Overview",
            None,
            "Return JSON exactly: {\"answer\": ...}. Evidence: Sources: Confidence:",
            0.20,
        ),
        (
            11,
            "cardB",
            Category.hands_on_engineering.value,
            "Overview",
            None,
            "Built an on-prem RAG platform.",
            0.205,
        ),
    ]
    monkeypatch.setattr(retrieval.psycopg, "connect", lambda *a, **k: _Conn(rows))

    class _Provider:
        def embed(self, texts: list[str]):
            return [[0.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(retrieval, "get_embedding_provider", lambda **k: _Provider())

    chunks = retrieval.retrieve_for_category(
        "q",
        Category.hands_on_engineering,
        budget=2,
    )
    assert len(chunks) == 2
    assert chunks[0].content.startswith("Built"), "factual chunk should outrank meta/policy chunk"
