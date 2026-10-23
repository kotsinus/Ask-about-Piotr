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

from app.embeddings import (
    EmbeddingProvider,
    OpenAIEmbeddingProvider,
    StubEmbeddingProvider,
    get_embedding_provider,
)
from app.llm import rewrite_question, route_category, synthesize_answer
from app.retrieval import RetrievedChunk
from app.routing_category import RoutingCategory
from app.schemas import Confidence


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
        # Return something plausibly standalone and specific enough to pass
        # language-agnostic ambiguity validation.
        return _chat_response(
            json.dumps(
                # Must not introduce new content tokens not present in
                # (original question ∪ history).
                {"standalone_question": "What about embeddings?"}
            )
        )

    monkeypatch.setattr("app.openai_client._client", None)
    monkeypatch.setattr(
        "app.openai_client.OpenAI",
        lambda api_key: _FakeOpenAI(api_key=api_key, create_impl=_create_impl),
    )

    out = rewrite_question(
        "What about that?",
        messages=[{"role": "user", "content": "We discussed embeddings."}],
    )
    assert "embedding" in out.lower()
    assert "?" in out


def test_rewrite_question_handles_non_json_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    monkeypatch.setattr("app.openai_client._client", None)
    monkeypatch.setattr(
        "app.openai_client.OpenAI",
        lambda api_key: _FakeOpenAI(
            api_key=api_key,
            create_impl=lambda **k: _chat_response("not-json"),
        ),
    )

    assert rewrite_question("Q", messages=[{"role": "user", "content": "x"}]) == "Q"


def test_rewrite_question_retries_on_ambiguous_or_unchanged_short_followup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Smoke: Q1 then Q2='what are they?' should be rewritten into an explicit standalone question."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    calls: list[int] = []

    def _create_impl(*, kind: str, **kwargs):
        assert kind == "chat"
        calls.append(1)
        # First attempt: unchanged + ambiguous (should trigger retry).
        if len(calls) == 1:
            return _chat_response(json.dumps({"standalone_question": "what are they?"}))
        # Second attempt: explicit and standalone.
        return _chat_response(
            json.dumps(
                {
                    # Must not introduce new content tokens not present in
                    # (original question ∪ history).
                    "standalone_question": "Which publications best represent your research focus?"
                }
            )
        )

    monkeypatch.setattr("app.openai_client._client", None)
    monkeypatch.setattr(
        "app.openai_client.OpenAI",
        lambda api_key: _FakeOpenAI(api_key=api_key, create_impl=_create_impl),
    )

    out = rewrite_question(
        "what are they?",
        messages=[
            {
                "role": "user",
                "content": "Which publications best represent your research focus?",
            }
        ],
    )

    assert "publication" in out.lower()
    assert "?" in out
    assert len(calls) >= 2


def test_rewrite_question_trimmed_history_standalone_does_not_add_new_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: when history is trimmed/small, do not rewrite standalone short questions into new facts/tokens."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    calls: list[int] = []

    def _create_impl(*, kind: str, **kwargs):
        assert kind == "chat"
        calls.append(1)
        # First attempt: model injects meta tokens that were not in original/history.
        if len(calls) == 1:
            return _chat_response(
                json.dumps(
                    {
                        "standalone_question": "What is your name as an AI language model?"
                    }
                )
            )
        # Second attempt: return unchanged original (allowed).
        return _chat_response(json.dumps({"standalone_question": "What is your name?"}))

    monkeypatch.setattr("app.openai_client._client", None)
    monkeypatch.setattr(
        "app.openai_client.OpenAI",
        lambda api_key: _FakeOpenAI(api_key=api_key, create_impl=_create_impl),
    )

    out = rewrite_question(
        "what is your name?",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert out.strip().lower() == "what is your name?"
    assert "language" not in out.lower()
    assert "model" not in out.lower()
    assert len(calls) >= 2


def test_rewrite_question_allows_derived_disambiguation_tokens_from_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: allow benign disambiguation words derived from recent context.

    Example: history contains "program" and the rewrite adds "programming" to
    disambiguate "What languages?".
    """

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def _create_impl(*, kind: str, **kwargs):
        assert kind == "chat"
        return _chat_response(
            json.dumps(
                {
                    "standalone_question": "What programming languages can you program in?"
                }
            )
        )

    monkeypatch.setattr("app.openai_client._client", None)
    monkeypatch.setattr(
        "app.openai_client.OpenAI",
        lambda api_key: _FakeOpenAI(api_key=api_key, create_impl=_create_impl),
    )

    out = rewrite_question(
        "What languages?",
        messages=[{"role": "user", "content": "Can you program?"}],
    )
    assert out == "What programming languages can you program in?"


def test_route_category_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        route_category("Q")


def test_route_category_parses_known_and_unknown_categories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    monkeypatch.setattr("app.openai_client._client", None)
    monkeypatch.setattr(
        "app.openai_client.OpenAI",
        lambda api_key: _FakeOpenAI(
            api_key=api_key,
            create_impl=lambda **k: _chat_response(
                json.dumps({"routing_category": "AI and ML practice"})
            ),
        ),
    )
    assert route_category("Q") == RoutingCategory.ai_and_ml_practice

    monkeypatch.setattr("app.openai_client._client", None)
    monkeypatch.setattr(
        "app.openai_client.OpenAI",
        lambda api_key: _FakeOpenAI(
            api_key=api_key,
            create_impl=lambda **k: _chat_response(
                json.dumps({"routing_category": "???"})
            ),
        ),
    )
    assert route_category("Q") == RoutingCategory.hands_on_engineering


def test_synthesize_answer_falls_back_to_all_indices_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    chunks = [
        RetrievedChunk(
            card_id="c1",
            card_category="skills",
            section="Overview",
            source_url=None,
            content="One. Two.",
        ),
        RetrievedChunk(
            card_id="c2",
            card_category="skills",
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

    monkeypatch.setattr("app.openai_client._client", None)
    monkeypatch.setattr(
        "app.openai_client.OpenAI",
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
            card_category="skills",
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

    monkeypatch.setattr("app.openai_client._client", None)
    monkeypatch.setattr(
        "app.openai_client.OpenAI",
        lambda api_key: _FakeOpenAI(api_key=api_key, create_impl=_create_impl),
    )

    texts = [" ", "a"] + [f"t{i}" for i in range(65)]
    out = provider.embed(texts)

    # Cleaned removes blanks => 66 inputs.
    assert len(out) == 66
    assert calls == [64, 2]

    with pytest.raises(RuntimeError, match="No valid text provided"):
        provider.embed([" ", "\n\n"])


def test_embeddings_base_and_stub_provider_raise() -> None:
    provider = EmbeddingProvider(name="x", dimensions=3)
    with pytest.raises(NotImplementedError):
        provider.embed(["x"])  # covers base interface branch

    stub = StubEmbeddingProvider(name="stub", dimensions=3)
    with pytest.raises(RuntimeError, match="stubbed"):
        stub.embed(["x"])
