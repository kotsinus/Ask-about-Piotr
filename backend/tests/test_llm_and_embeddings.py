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
# Unit tests for LLM-facing code paths using a fake OpenAI client.

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.embeddings import OpenAIEmbeddingProvider, get_embedding_provider
from app.llm import rewrite_question, route_category, synthesize_answer
from app.retrieval import RetrievedChunk
from app.schemas import Category, Confidence


class _FakeOpenAI:
    def __init__(self, *, api_key: str, create_impl):
        self.api_key = api_key
        self._create_impl = create_impl

        class _Chat:
            def __init__(self, outer):
                self.completions = outer

        self.chat = _Chat(self)

        class _Embeddings:
            def __init__(self, outer):
                self._outer = outer

            def create(self, *, model: str, input: list[str]):
                return outer._create_impl(kind="embeddings", model=model, input=input)

        outer = self
        self.embeddings = _Embeddings(self)

    def create(self, **kwargs):
        return self._create_impl(kind="chat", **kwargs)


def _chat_response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_rewrite_question_returns_original_when_no_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert rewrite_question("Q", messages=[{"role": "user", "content": "x"}]) == "Q"


def test_rewrite_question_uses_openai_when_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def _create_impl(*, kind: str, **kwargs):
        assert kind == "chat"
        return _chat_response(json.dumps({"standalone_question": "Standalone?"}))

    monkeypatch.setattr(
        "app.llm.OpenAI",
        lambda api_key: _FakeOpenAI(api_key=api_key, create_impl=_create_impl),
    )

    out = rewrite_question(
        "What about that?",
        messages=[{"role": "user", "content": "We discussed embeddings."}],
    )
    assert out == "Standalone?"


def test_rewrite_question_handles_non_json_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    monkeypatch.setattr(
        "app.llm.OpenAI",
        lambda api_key: _FakeOpenAI(
            api_key=api_key,
            create_impl=lambda **k: _chat_response("not-json"),
        ),
    )

    assert rewrite_question("Q", messages=[{"role": "user", "content": "x"}]) == "Q"


def test_route_category_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        route_category("Q")


def test_route_category_parses_known_and_unknown_categories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    monkeypatch.setattr(
        "app.llm.OpenAI",
        lambda api_key: _FakeOpenAI(
            api_key=api_key,
            create_impl=lambda **k: _chat_response(
                json.dumps({"category": "AI and ML practice"})
            ),
        ),
    )
    assert route_category("Q") == Category.ai_and_ml_practice

    monkeypatch.setattr(
        "app.llm.OpenAI",
        lambda api_key: _FakeOpenAI(
            api_key=api_key,
            create_impl=lambda **k: _chat_response(json.dumps({"category": "???"})),
        ),
    )
    assert route_category("Q") == Category.hands_on_engineering


def test_synthesize_answer_falls_back_to_all_indices_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    chunks = [
        RetrievedChunk(
            card_id="c1",
            category="skills",
            section="Overview",
            source_url=None,
            content="One. Two.",
        ),
        RetrievedChunk(
            card_id="c2",
            category="skills",
            section="Details",
            source_url=None,
            content="Three. Four.",
        ),
    ]

    payload = {
        "answer": "An answer grounded in evidence.",
        "why_this_matters": "",
        "confidence": "Low",
        "confidence_reason": "Because reasons.",
        # used_chunk_indices missing => should fall back to all.
    }

    monkeypatch.setattr(
        "app.llm.OpenAI",
        lambda api_key: _FakeOpenAI(
            api_key=api_key,
            create_impl=lambda **k: _chat_response(json.dumps(payload)),
        ),
    )

    result = synthesize_answer("Q", chunks)
    assert result.answer == "An answer grounded in evidence."
    assert (
        result.why_this_matters
        == "This answer is grounded in retrieved knowledge cards."
    )
    assert result.confidence == Confidence.low
    assert result.confidence_reason == "Because reasons."
    assert result.used_chunk_indices == [0, 1]


def test_synthesize_answer_uses_deterministic_fallback_when_no_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    chunks = [
        RetrievedChunk(
            card_id="c1",
            category="skills",
            section="Overview",
            source_url=None,
            content="First. Second! Third? Fourth.",
        )
    ]
    result = synthesize_answer("Q", chunks)
    assert result.confidence == Confidence.medium
    assert result.used_chunk_indices == [0]
    assert "First." in result.answer


def test_get_embedding_provider_routes_and_openai_provider_requires_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = get_embedding_provider("stub", 3)
    assert stub.name == "stub"

    provider = get_embedding_provider("openai", 3)
    assert isinstance(provider, OpenAIEmbeddingProvider)

    with pytest.raises(ValueError, match="Unsupported embeddings provider"):
        get_embedding_provider("nope", 3)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        provider.embed(["hello"])


def test_openai_embedding_provider_batches_and_filters_empty_texts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = OpenAIEmbeddingProvider(name="openai", dimensions=1)

    calls: list[int] = []

    def _create_impl(*, kind: str, model: str, input: list[str], **kwargs):
        assert kind == "embeddings"
        calls.append(len(input))
        # One scalar per input item; keep deterministic ordering.
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[float(i)]) for i in range(len(input))]
        )

    monkeypatch.setattr(
        "app.embeddings.OpenAI",
        lambda api_key: _FakeOpenAI(api_key=api_key, create_impl=_create_impl),
    )

    texts = [" ", "a"] + [f"t{i}" for i in range(65)]
    out = provider.embed(texts)

    # Cleaned removes blanks => 66 inputs.
    assert len(out) == 66
    assert calls == [64, 2]

    with pytest.raises(RuntimeError, match="No valid text provided"):
        provider.embed([" ", "\n\n"])
