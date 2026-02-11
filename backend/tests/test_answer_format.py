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
# Verifies strict answer formatting and no-evidence behavior.

from __future__ import annotations

import httpx
import pytest

from app.main import app
from app.retrieval import RetrievedChunk
from app.schemas import Confidence


@pytest.mark.anyio
async def test_no_evidence_response(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

        def _stub_retrieve(
            question: str, limit: int = 5, conversation_topic: str | None = None
        ) -> list[RetrievedChunk]:
            return []

        monkeypatch.setattr("app.main.retrieve", _stub_retrieve)

        response = await client.post(
            "/chat", json={"question": "What is Piotr's role?"}
        )
        assert response.status_code == 200
        payload = response.json()

        assert (
            payload["answer"]
            == "I do not have enough evidence in the provided materials."
        )
        assert payload["confidence"] == "Low"
        assert "Confidence" in payload["formatted_answer"]
        assert payload["evidence"] == []


@pytest.mark.anyio
async def test_formatted_answer_contains_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

        def _stub_retrieve(
            question: str, limit: int = 5, conversation_topic: str | None = None
        ) -> list[RetrievedChunk]:
            return [
                RetrievedChunk(
                    card_id="sample",
                    category="project",
                    section="Problem",
                    source_url=None,
                    content="This is a test chunk.",
                )
            ]

        monkeypatch.setattr("app.main.retrieve", _stub_retrieve)

        response = await client.post("/chat", json={"question": "What did you build?"})
        assert response.status_code == 200
        formatted = response.json()["formatted_answer"]

        for header in [
            "Answer:",
            "Why this matters:",
            "Evidence:",
            "Sources:",
            "Confidence:",
        ]:
            assert header in formatted


@pytest.mark.anyio
async def test_followup_question_uses_history_rewrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ambiguous follow-up should be rewritten into a standalone question before retrieval."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

        def _stub_rewrite(question: str, messages: list[dict] | None = None) -> str:
            # Simulate an LLM rewrite resolving the follow-up "In what languages?"
            # using prior context about programming.
            if question.strip().lower() == "in what languages?":
                return "In what programming languages can Piotr program?"
            return question

        def _stub_retrieve(
            question: str, limit: int = 5, conversation_topic: str | None = None
        ) -> list[RetrievedChunk]:
            if "program" in question.lower():
                return [
                    RetrievedChunk(
                        card_id="skills-programming-languages",
                        category="skills",
                        section="Overview",
                        source_url=None,
                        content="Piotr programs primarily in Python and TypeScript.",
                    )
                ]
            return [
                RetrievedChunk(
                    card_id="skills-spoken-languages",
                    category="skills",
                    section="Overview",
                    source_url=None,
                    content="Piotr speaks Polish and English.",
                )
            ]

        monkeypatch.setattr("app.main.rewrite_question", _stub_rewrite)
        monkeypatch.setattr("app.main.retrieve", _stub_retrieve)

        response = await client.post(
            "/chat",
            json={
                "question": "In what languages?",
                "messages": [
                    {"role": "user", "content": "Can you program?"},
                    {"role": "assistant", "content": "Yes."},
                ],
            },
        )
        assert response.status_code == 200
        payload = response.json()

        assert "Python" in payload["answer"]
        assert "TypeScript" in payload["answer"]
        assert "Polish" not in payload["answer"]


@pytest.mark.anyio
async def test_evidence_and_sources_include_only_used_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        chunks = [
            RetrievedChunk(
                card_id="c1",
                category="skills",
                section="Overview",
                source_url=None,
                content="Chunk 0",
                distance=0.10,
            ),
            RetrievedChunk(
                card_id="c2",
                category="skills",
                section="Details",
                source_url=None,
                content="Chunk 1 (used)",
                distance=0.11,
            ),
            RetrievedChunk(
                card_id="c3",
                category="skills",
                section="More",
                source_url=None,
                content="Chunk 2",
                distance=0.12,
            ),
        ]

        def _stub_retrieve(
            question: str, limit: int = 5, conversation_topic: str | None = None
        ) -> list[RetrievedChunk]:
            return chunks

        class _StubSynthesis:
            answer = (
                "- Chunk 1 (used)\n"
                "- Chunk 1 is the only evidence I used\n\n"
                "Short synthesis."
            )
            why_this_matters = "It matters because the chunk evidence supports this answer."
            confidence = Confidence.medium
            confidence_reason = None
            used_chunk_indices = [1]

        def _stub_synthesize_answer(*args, **kwargs):
            return _StubSynthesis()

        monkeypatch.setattr("app.main.retrieve", _stub_retrieve)
        monkeypatch.setattr("app.main.synthesize_answer", _stub_synthesize_answer)

        response = await client.post("/chat?debug_retrieval=1", json={"question": "Q"})
        assert response.status_code == 200
        payload = response.json()

        assert payload["evidence"] == [{"snippet": "Chunk 1 (used)", "card_id": "c2"}]
        assert payload["sources"] == [{"card_id": "c2", "section": "Details"}]
        assert payload["debug_retrieval"] == [
            {"card_id": "c1", "section": "Overview", "distance": 0.10},
            {"card_id": "c2", "section": "Details", "distance": 0.11},
            {"card_id": "c3", "section": "More", "distance": 0.12},
        ]


@pytest.mark.anyio
async def test_answer_starts_with_facts_bullets_when_non_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

        def _stub_retrieve(
            question: str, limit: int = 5, conversation_topic: str | None = None
        ) -> list[RetrievedChunk]:
            return [
                RetrievedChunk(
                    card_id="c1",
                    category="skills",
                    section="Overview",
                    source_url=None,
                    content="Piotr programs primarily in Python and TypeScript.",
                ),
                RetrievedChunk(
                    card_id="c2",
                    category="skills",
                    section="More",
                    source_url=None,
                    content="He also works with Postgres and Docker.",
                ),
            ]

        class _StubSynthesis:
            answer = "- Python and TypeScript\n- Postgres and Docker\n\nI focus on practical engineering work."
            why_this_matters = "Test"
            confidence = Confidence.medium
            confidence_reason = None
            used_chunk_indices = [0, 1]

        monkeypatch.setattr("app.main.retrieve", _stub_retrieve)
        monkeypatch.setattr("app.main.synthesize_answer", lambda *a, **k: _StubSynthesis())

        response = await client.post("/chat", json={"question": "What do you use?"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["answer"].lstrip().startswith("-")
        assert "\n\n" in payload["answer"]
