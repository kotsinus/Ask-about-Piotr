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
            "education-overview",
            "education",
            "Overview",
            None,
            "Piotr's education includes formal study and continued learning.",
            0.45,
        ),
        (
            "education-facts",
            "education",
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
