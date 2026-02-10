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
# Server-side synthesis quality gates + retry behavior.

from __future__ import annotations

import httpx
import pytest

from app.main import app
from app.retrieval import RetrievedChunk
from app.schemas import Confidence


@pytest.mark.anyio
async def test_quality_gate_triggers_retry_on_too_short_and_uses_retry_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

        def _stub_retrieve(
            question: str, limit: int = 25, conversation_topic: str | None = None
        ) -> list[RetrievedChunk]:
            return [
                RetrievedChunk(
                    card_id="education-facts",
                    category="education",
                    section="Degrees",
                    source_url=None,
                    content="MSc at Example University.",
                    best_origin_category="Education and formal background",
                ),
                RetrievedChunk(
                    card_id="project-onprem-rag-platform",
                    category="project",
                    section="What I built",
                    source_url=None,
                    content="Built an on-prem RAG platform.",
                    best_origin_category="Hands-on engineering",
                ),
            ]

        monkeypatch.setattr("app.main.retrieve", _stub_retrieve)

        calls: dict[str, int] = {"n": 0}

        class _S0:
            answer = "Yes"
            why_this_matters = "x"
            confidence = Confidence.medium
            confidence_reason = None
            used_chunk_indices = []

        class _S1:
            answer = (
                "- Yes: I have formal education evidence.\n"
                "- On‑prem RAG platform: built and shipped a system.\n\n"
                "I can ground both education and hands-on experience in the provided notes."
            )
            why_this_matters = "x"
            confidence = Confidence.medium
            confidence_reason = None
            used_chunk_indices = [0, 1]

        def _stub_synthesize_answer(*args, **kwargs):
            calls["n"] += 1
            return _S0() if calls["n"] == 1 else _S1()

        monkeypatch.setattr("app.main.synthesize_answer", _stub_synthesize_answer)

        resp = await client.post(
            "/chat?debug_retrieval=1",
            json={"question": "Tell me about your education and what you built."},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert calls["n"] == 2, "quality gate must retry once"
        assert payload["answer"].lstrip().startswith("-")
        assert payload["evidence"], "should include evidence for used indices"


@pytest.mark.anyio
async def test_retry_failure_triggers_deterministic_fallback_and_stays_grounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

        def _stub_retrieve(
            question: str, limit: int = 25, conversation_topic: str | None = None
        ) -> list[RetrievedChunk]:
            return [
                RetrievedChunk(
                    card_id="c1",
                    category="project",
                    section="Overview",
                    source_url=None,
                    content="Chunk A. Chunk B. Chunk C.",
                    best_origin_category="Hands-on engineering",
                )
            ]

        monkeypatch.setattr("app.main.retrieve", _stub_retrieve)

        calls: dict[str, int] = {"n": 0}

        class _Bad:
            answer = "I am a great fit."
            why_this_matters = "x"
            confidence = Confidence.medium
            confidence_reason = None
            used_chunk_indices = []

        def _stub_synthesize_answer(*args, **kwargs):
            calls["n"] += 1
            return _Bad()

        monkeypatch.setattr("app.main.synthesize_answer", _stub_synthesize_answer)

        resp = await client.post("/chat", json={"question": "What did you build?"})
        assert resp.status_code == 200
        payload = resp.json()
        assert calls["n"] == 2
        # Deterministic fallback is facts-first now.
        assert payload["answer"].lstrip().startswith("-")
        assert "Chunk" in payload["answer"], "fallback must be grounded in chunk text"


@pytest.mark.anyio
async def test_category_coverage_gate_enforced_when_two_categories_have_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

        chunks = [
            RetrievedChunk(
                card_id="education-facts",
                category="education",
                section="Degrees",
                source_url=None,
                content="MSc at Example University.",
                best_origin_category="Education and formal background",
            ),
            RetrievedChunk(
                card_id="project-onprem-rag-platform",
                category="project",
                section="What I built",
                source_url=None,
                content="Built an on-prem RAG platform.",
                best_origin_category="Hands-on engineering",
            ),
        ]

        def _stub_retrieve(
            question: str, limit: int = 25, conversation_topic: str | None = None
        ) -> list[RetrievedChunk]:
            return chunks

        monkeypatch.setattr("app.main.retrieve", _stub_retrieve)

        calls: dict[str, int] = {"n": 0}

        class _OnlyEdu:
            answer = "- Example University: MSc degree.\n- Another edu fact here.\n\nShort synthesis."
            why_this_matters = "x"
            confidence = Confidence.medium
            confidence_reason = None
            used_chunk_indices = [0]

        class _Both:
            answer = (
                "- Example University: MSc degree.\n"
                "- On‑prem RAG platform: built and deployed it.\n\n"
                "Synthesis uses both education and hands-on evidence."
            )
            why_this_matters = "x"
            confidence = Confidence.medium
            confidence_reason = None
            used_chunk_indices = [0, 1]

        def _stub_synthesize_answer(*args, **kwargs):
            calls["n"] += 1
            return _OnlyEdu() if calls["n"] == 1 else _Both()

        monkeypatch.setattr("app.main.synthesize_answer", _stub_synthesize_answer)

        resp = await client.post(
            "/chat",
            json={"question": "Tell me about your education and engineering experience."},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert calls["n"] == 2
        assert len(payload["evidence"]) == 2


@pytest.mark.anyio
async def test_non_yesno_question_starting_with_yes_triggers_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

        def _stub_retrieve(
            question: str, limit: int = 25, conversation_topic: str | None = None
        ) -> list[RetrievedChunk]:
            return [
                RetrievedChunk(
                    card_id="c1",
                    category="skills",
                    section="Overview",
                    source_url=None,
                    content="Piotr programs in Python.",
                    best_origin_category="Hands-on engineering",
                )
            ]

        monkeypatch.setattr("app.main.retrieve", _stub_retrieve)

        calls: dict[str, int] = {"n": 0}

        class _Bad:
            answer = "- Yes: definitely.\n- Another bullet.\n\nSynthesis."
            why_this_matters = "x"
            confidence = Confidence.medium
            confidence_reason = None
            used_chunk_indices = [0]

        class _Ok:
            answer = "- Python: I program in Python.\n- Grounded fact.\n\nShort synthesis."
            why_this_matters = "x"
            confidence = Confidence.medium
            confidence_reason = None
            used_chunk_indices = [0]

        def _stub_synthesize_answer(*args, **kwargs):
            calls["n"] += 1
            return _Bad() if calls["n"] == 1 else _Ok()

        monkeypatch.setattr("app.main.synthesize_answer", _stub_synthesize_answer)

        resp = await client.post(
            "/chat",
            json={"question": "What is your primary programming language?"},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert calls["n"] == 2
        assert not payload["answer"].lstrip().lower().startswith("- yes")
