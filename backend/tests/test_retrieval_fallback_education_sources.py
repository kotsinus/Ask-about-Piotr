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
# Regression test: retrieval must not return zero sources when relevant
# candidates exist but strict distance cutoffs filter everything out.

from __future__ import annotations

import httpx
import pytest

from app.main import app
from app import retrieval
from app.schemas import Category


@pytest.mark.anyio
async def test_education_query_returns_sources_and_evidence_with_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Force cutoffs that would filter out all reasonable candidates.
    monkeypatch.setenv("RETRIEVAL_MAX_DISTANCE", "0.0")
    monkeypatch.setenv("RETRIEVAL_DISTANCE_DELTA", "0.0")

    # Stub embeddings (avoid the default stub provider raising).
    class _StubEmbeddingProvider:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(
        "app.retrieval.get_embedding_provider",
        lambda name, dimensions: _StubEmbeddingProvider(),
    )

    # Stub DB access: return education candidates with distances that will be
    # filtered out by the strict cutoffs above.
    rows = [
        (
            101,
            "education-overview",
            Category.education_and_formal_background.value,
            "Overview",
            None,
            "Piotr's education includes formal study and continued learning.",
            0.45,
        ),
        (
            102,
            "education-facts",
            Category.education_and_formal_background.value,
            "Facts",
            None,
            "Selected education facts are captured as structured notes.",
            0.46,
        ),
    ]

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            return None

        def fetchall(self):
            return rows

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return _Cursor()

    monkeypatch.setattr("app.retrieval.register_vector", lambda conn: None)
    monkeypatch.setattr(
        "app.retrieval.psycopg.connect", lambda *args, **kwargs: _Conn()
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat", json={"question": "What is your education?"}
        )
        assert response.status_code == 200
        payload = response.json()

        assert payload["sources"], "Expected non-empty sources for an education query."
        assert payload["evidence"], (
            "Expected non-empty evidence for an education query."
        )

        source_card_ids = {item["card_id"] for item in payload["sources"]}
        evidence_card_ids = {item["card_id"] for item in payload["evidence"]}

        assert any(card_id.startswith("education-") for card_id in source_card_ids)
        assert any(card_id.startswith("education-") for card_id in evidence_card_ids)


def test_merge_pin_education_facts_evicts_weakest_non_pinned_under_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No changes to main orchestration yet; test pinning at retrieval-utility level.
    per_category = {
        Category.education_and_formal_background.value: [
            retrieval.RetrievedChunk(
                chunk_id=1,
                card_id="education-overview",
                category=Category.education_and_formal_background.value,
                section="Overview",
                content="edu overview",
                distance=0.10,
                adjusted_distance=0.10,
                best_origin_category=Category.education_and_formal_background.value,
                origin_categories=[Category.education_and_formal_background.value],
            )
        ],
        Category.hands_on_engineering.value: [
            retrieval.RetrievedChunk(
                chunk_id=2,
                card_id="project-onprem-rag-platform",
                category=Category.hands_on_engineering.value,
                section="What I built",
                content="eng chunk",
                distance=0.11,
                adjusted_distance=0.11,
                best_origin_category=Category.hands_on_engineering.value,
                origin_categories=[Category.hands_on_engineering.value],
            )
        ],
    }

    def _stub_pin(*args, **kwargs):
        return [
            retrieval.RetrievedChunk(
                chunk_id=3,
                card_id="education-facts",
                category=Category.education_and_formal_background.value,
                section="Facts",
                content="edu facts",
                distance=0.12,
                adjusted_distance=0.12,
            )
        ]

    monkeypatch.setattr(retrieval, "retrieve_for_category", _stub_pin)

    merged = retrieval.merge_dedup_pin_and_cap(
        question="Tell me about your education and one project.",
        per_category_selected=per_category,
        routed_categories=[
            Category.education_and_formal_background,
            Category.hands_on_engineering,
        ],
        max_total_chunks=2,
    )

    card_ids = [c.card_id for c in merged]
    # The pinned facts chunk must be present.
    assert "education-facts" in card_ids
    # Coverage: do not evict the only chunk for a routed category (engineering).
    assert "project-onprem-rag-platform" in card_ids
    # Evict weakest non-pinned from the over-represented category (education).
    assert "education-overview" not in card_ids
