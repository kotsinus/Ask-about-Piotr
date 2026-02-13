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


def test_merge_dedup_preserves_provenance_and_keeps_best_distance() -> None:
    chunk_a = retrieval.RetrievedChunk(
        card_id="c1",
        category="cat",
        section="Overview",
        source_url=None,
        content="Same content",
        distance=0.20,
        origin_categories=["Education and formal background"],
        best_origin_category="Education and formal background",
    )
    chunk_b = retrieval.RetrievedChunk(
        card_id="c1",
        category="cat",
        section="Overview",
        source_url=None,
        content="Same content",
        distance=0.10,
        origin_categories=["Hands-on engineering"],
        best_origin_category="Hands-on engineering",
    )

    merged, collisions = retrieval.merge_dedup_preserve_provenance(
        {
            "Education and formal background": [chunk_a],
            "Hands-on engineering": [chunk_b],
        }
    )

    assert collisions == 1
    assert len(merged) == 1
    assert merged[0].distance == 0.10
    assert set(merged[0].origin_categories or []) == {
        "Education and formal background",
        "Hands-on engineering",
    }


def test_cap_chunks_with_coverage_prefers_eviction_from_overrepresented_category() -> (
    None
):
    chunks = [
        retrieval.RetrievedChunk(
            card_id="a1",
            category="x",
            section="S",
            content="A1",
            distance=0.10,
            origin_categories=["Education and formal background"],
            best_origin_category="Education and formal background",
        ),
        retrieval.RetrievedChunk(
            card_id="a2",
            category="x",
            section="S",
            content="A2",
            distance=0.20,
            origin_categories=["Education and formal background"],
            best_origin_category="Education and formal background",
        ),
        retrieval.RetrievedChunk(
            card_id="b1",
            category="y",
            section="S",
            content="B1",
            distance=0.15,
            origin_categories=["Hands-on engineering"],
            best_origin_category="Hands-on engineering",
        ),
    ]

    capped = retrieval.cap_chunks_with_coverage(
        chunks=chunks,
        routed_categories=["Education and formal background", "Hands-on engineering"],
        max_total_chunks=2,
    )
    assert len(capped) == 2
    best_origins = {c.best_origin_category for c in capped}
    assert best_origins == {"Education and formal background", "Hands-on engineering"}


def test_apply_pinning_adds_missing_card() -> None:
    """Given chunks without the pinned card, when pinning rules require a specific
    card for a category, then the card is added to chunks with pinned=True."""
    existing_chunk = retrieval.RetrievedChunk(
        card_id="other-card",
        category="Other",
        section="Summary",
        content="Some content",
        distance=0.2,
        origin_categories=["Other category"],
        best_origin_category="Other category",
    )
    chunks = [existing_chunk]

    pinning_rules = {"Education and formal background": ["education-facts"]}
    routed_categories = ["Education and formal background"]

    def mock_retrieve_for_card(
        card_id: str, limit: int
    ) -> list[retrieval.RetrievedChunk]:
        return [
            retrieval.RetrievedChunk(
                card_id=card_id,
                category="Education",
                section="Degrees",
                content="Education content",
                distance=0.3,
                origin_categories=["Education and formal background"],
                best_origin_category="Education and formal background",
            )
        ]

    result, pinned_ids = retrieval.apply_pinning(
        chunks=chunks,
        pinning_rules=pinning_rules,
        routed_categories=routed_categories,
        retrieve_for_card_fn=mock_retrieve_for_card,
    )

    assert len(result) == 2
    assert "education-facts" in pinned_ids
    assert any(c.pinned for c in result)
    pinned_chunk = next(c for c in result if c.card_id == "education-facts")
    assert pinned_chunk.pinned is True


def test_apply_pinning_skips_if_card_already_present() -> None:
    """Given chunks already contain a chunk from the pinned card, when pinning
    rules require that card, then no duplicate is added, existing chunk is not modified."""
    existing_chunk = retrieval.RetrievedChunk(
        card_id="education-facts",
        category="Education",
        section="Degrees",
        content="Existing education content",
        distance=0.15,
        origin_categories=["Education and formal background"],
        best_origin_category="Education and formal background",
        pinned=False,
    )
    chunks = [existing_chunk]

    pinning_rules = {"Education and formal background": ["education-facts"]}
    routed_categories = ["Education and formal background"]

    call_count = 0

    def mock_retrieve_for_card(
        card_id: str, limit: int
    ) -> list[retrieval.RetrievedChunk]:
        nonlocal call_count
        call_count += 1
        return [
            retrieval.RetrievedChunk(
                card_id=card_id,
                category="Education",
                section="Other",
                content="Should not be added",
                distance=0.5,
                origin_categories=["Education and formal background"],
                best_origin_category="Education and formal background",
            )
        ]

    result, pinned_ids = retrieval.apply_pinning(
        chunks=chunks,
        pinning_rules=pinning_rules,
        routed_categories=routed_categories,
        retrieve_for_card_fn=mock_retrieve_for_card,
    )

    assert len(result) == 1
    assert len(pinned_ids) == 0
    assert call_count == 0  # retrieve_for_card should not be called
    assert result[0].pinned is False  # existing chunk should not be modified


def test_apply_pinning_multiple_categories() -> None:
    """Given multiple routed categories with different pinning rules, when pinning
    is applied, then all required cards are pinned."""
    existing_chunk = retrieval.RetrievedChunk(
        card_id="other-card",
        category="Other",
        section="Summary",
        content="Some content",
        distance=0.2,
        origin_categories=["Other category"],
        best_origin_category="Other category",
    )
    chunks = [existing_chunk]

    pinning_rules = {
        "Education and formal background": ["education-facts"],
        "Certifications": ["certifications-facts"],
    }
    routed_categories = ["Education and formal background", "Certifications"]

    def mock_retrieve_for_card(
        card_id: str, limit: int
    ) -> list[retrieval.RetrievedChunk]:
        category_map = {
            "education-facts": "Education and formal background",
            "certifications-facts": "Certifications",
        }
        return [
            retrieval.RetrievedChunk(
                card_id=card_id,
                category=card_id.replace("-", " ").title(),
                section="Overview",
                content=f"Content for {card_id}",
                distance=0.3,
                origin_categories=[category_map.get(card_id, "Unknown")],
                best_origin_category=category_map.get(card_id, "Unknown"),
            )
        ]

    result, pinned_ids = retrieval.apply_pinning(
        chunks=chunks,
        pinning_rules=pinning_rules,
        routed_categories=routed_categories,
        retrieve_for_card_fn=mock_retrieve_for_card,
    )

    assert len(result) == 3  # 1 existing + 2 pinned
    assert len(pinned_ids) == 2
    assert "education-facts" in pinned_ids
    assert "certifications-facts" in pinned_ids
    pinned_chunks = [c for c in result if c.pinned]
    assert len(pinned_chunks) == 2


def test_apply_pinning_empty_rules() -> None:
    """Given empty pinning rules dict, when pinning is applied, then chunks are unchanged."""
    existing_chunk = retrieval.RetrievedChunk(
        card_id="some-card",
        category="Some",
        section="Summary",
        content="Some content",
        distance=0.2,
        origin_categories=["Some category"],
        best_origin_category="Some category",
    )
    chunks = [existing_chunk]

    pinning_rules: dict[str, list[str]] = {}
    routed_categories = ["Education and formal background"]

    def mock_retrieve_for_card(
        card_id: str, limit: int
    ) -> list[retrieval.RetrievedChunk]:
        raise AssertionError("Should not be called with empty rules")

    result, pinned_ids = retrieval.apply_pinning(
        chunks=chunks,
        pinning_rules=pinning_rules,
        routed_categories=routed_categories,
        retrieve_for_card_fn=mock_retrieve_for_card,
    )

    assert len(result) == 1
    assert len(pinned_ids) == 0
    assert result[0].card_id == "some-card"


def test_apply_pinning_no_matching_category() -> None:
    """Given pinning rules for categories not in routed_categories, when pinning
    is applied, then chunks are unchanged."""
    existing_chunk = retrieval.RetrievedChunk(
        card_id="some-card",
        category="Some",
        section="Summary",
        content="Some content",
        distance=0.2,
        origin_categories=["Some category"],
        best_origin_category="Some category",
    )
    chunks = [existing_chunk]

    # Pinning rules for categories that are NOT in routed_categories
    pinning_rules = {
        "Education and formal background": ["education-facts"],
        "Certifications": ["certifications-facts"],
    }
    routed_categories = ["Leadership", "Research"]  # Different categories

    def mock_retrieve_for_card(
        card_id: str, limit: int
    ) -> list[retrieval.RetrievedChunk]:
        raise AssertionError("Should not be called when no categories match")

    result, pinned_ids = retrieval.apply_pinning(
        chunks=chunks,
        pinning_rules=pinning_rules,
        routed_categories=routed_categories,
        retrieve_for_card_fn=mock_retrieve_for_card,
    )

    assert len(result) == 1
    assert len(pinned_ids) == 0
    assert result[0].card_id == "some-card"
