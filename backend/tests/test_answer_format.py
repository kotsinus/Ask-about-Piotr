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

from typing import List

import httpx
import pytest

from app.main import app
from app.retrieval import RetrievedChunk


@pytest.mark.anyio
async def test_no_evidence_response(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        def _stub_retrieve(question: str) -> List[RetrievedChunk]:
            return []

        monkeypatch.setattr("app.main.retrieve", _stub_retrieve)

        response = await client.post("/chat", json={"question": "What is Piotr's role?"})
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
        def _stub_retrieve(question: str) -> List[RetrievedChunk]:
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

