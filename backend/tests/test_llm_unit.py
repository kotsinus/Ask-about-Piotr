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
# Unit tests for LLM helpers focused on parsing and fallbacks (no network).

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app import llm
from app.retrieval import RetrievedChunk
from app.schemas import Category, Confidence


class _FakeOpenAI:
    def __init__(self, *, content: str, capture: dict | None = None) -> None:
        self._content = content
        self._capture = capture

        class _Completions:
            def __init__(self, outer: _FakeOpenAI) -> None:
                self._outer = outer

            def create(self, **kwargs):
                if self._outer._capture is not None:
                    self._outer._capture["kwargs"] = kwargs

                class _Msg:
                    def __init__(self, content: str) -> None:
                        self.content = content

                class _Choice:
                    def __init__(self, content: str) -> None:
                        self.message = _Msg(content)

                class _Resp:
                    def __init__(self, content: str) -> None:
                        self.choices = [_Choice(content)]

                return _Resp(self._outer._content)

        class _Chat:
            def __init__(self, outer: _FakeOpenAI) -> None:
                self.completions = _Completions(outer)

        self.chat = _Chat(self)


def _settings(**overrides):
    base = SimpleNamespace(
        openai_api_key="test-key",
        router_model="router",
        synthesis_model="synth",
        synthesis_temperature=0.1,
        prompt_cache_enabled=False,
        embeddings_model=None,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_synthesize_answer_includes_context_and_topic_in_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict[str, object] = {}
    payload = {
        "answer": "Some sufficiently long answer that is not a refusal.",
        "why_this_matters": "Because.",
        "confidence": "Low",
        "confidence_reason": "Limited evidence.",
        "used_chunk_indices": ["0"],
    }
    monkeypatch.setattr(llm, "get_settings", lambda: _settings())
    monkeypatch.setattr("app.openai_client.get_settings", lambda: _settings())
    monkeypatch.setattr("app.openai_client._client", None)
    monkeypatch.setattr(
        "app.openai_client.OpenAI",
        lambda api_key: _FakeOpenAI(content=json.dumps(payload), capture=capture),
    )

    chunks = [
        RetrievedChunk(
            card_id="c1",
            category="cat",
            section="Overview",
            source_url=None,
            content="Evidence sentence one. Evidence sentence two.",
            distance=0.1,
        )
    ]

    result = llm.synthesize_answer(
        "q",
        chunks,
        conversation_topic="topic",
        conversation_messages=[{"role": "user", "content": "hi"}],
    )
    assert result.confidence == Confidence.low
    assert result.confidence_reason == "Limited evidence."

    user_msg = capture["kwargs"]["messages"][1]["content"]  # type: ignore[index]
    assert "Conversation context" in user_msg
    assert "Conversation topic: topic" in user_msg


def test_synthesize_answer_falls_back_when_answer_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "answer": " ",
        "why_this_matters": "",
        "confidence": "High",
        "confidence_reason": None,
        "used_chunk_indices": [],
    }
    monkeypatch.setattr(llm, "get_settings", lambda: _settings())
    monkeypatch.setattr("app.openai_client.get_settings", lambda: _settings())
    monkeypatch.setattr("app.openai_client._client", None)
    monkeypatch.setattr(
        "app.openai_client.OpenAI",
        lambda api_key: _FakeOpenAI(content=json.dumps(payload)),
    )

    chunks = [
        RetrievedChunk(
            card_id="c1",
            category="cat",
            section="Overview",
            source_url=None,
            content="One. Two.",
            distance=0.1,
        )
    ]
    result = llm.synthesize_answer("q", chunks)
    assert result.answer
    assert result.used_chunk_indices == [0]


def test_synthesize_answer_indices_non_list_falls_back_to_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "answer": "Some sufficiently long answer that is not a refusal.",
        "why_this_matters": "",
        "confidence": "Medium",
        "confidence_reason": "ignored",
        "used_chunk_indices": "not-a-list",
    }
    monkeypatch.setattr(llm, "get_settings", lambda: _settings())
    monkeypatch.setattr("app.openai_client.get_settings", lambda: _settings())
    monkeypatch.setattr("app.openai_client._client", None)
    monkeypatch.setattr(
        "app.openai_client.OpenAI",
        lambda api_key: _FakeOpenAI(content=json.dumps(payload)),
    )

    chunks = [
        RetrievedChunk(
            card_id="c1",
            category="cat",
            section="Overview",
            source_url=None,
            content="One. Two.",
            distance=0.1,
        ),
        RetrievedChunk(
            card_id="c2",
            category="cat",
            section="Details",
            source_url=None,
            content="Three. Four.",
            distance=0.2,
        ),
    ]
    result = llm.synthesize_answer("q", chunks)
    assert result.used_chunk_indices == [0, 1]


def test_rewrite_question_returns_original_on_bad_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm, "get_settings", lambda: _settings())
    monkeypatch.setattr("app.openai_client.get_settings", lambda: _settings())
    monkeypatch.setattr("app.openai_client._client", None)
    monkeypatch.setattr(
        "app.openai_client.OpenAI",
        lambda api_key: _FakeOpenAI(content="{bad json"),
    )
    assert llm.rewrite_question("q", messages=[{"role": "user", "content": "x"}]) == "q"


def test_clean_why_soft_removes_banned_phrases_without_constant_fallback() -> None:
    text = "This highlights the reliability trade-offs in production systems."
    out = llm.clean_why(text, Category.hands_on_engineering)
    assert "highlights" not in out.lower()
    assert "reliability" in out.lower()


def test_clean_why_uses_category_specific_fallback_when_too_short() -> None:
    out = llm.clean_why("It demonstrates.", Category.education_and_formal_background)
    assert out in {
        "It gives a foundation I rely on when reasoning about systems and data.",
        "It provides background that shapes how I approach technical problems.",
    }


def test_clean_why_empty_returns_category_specific_fallback() -> None:
    out = llm.clean_why(" ", Category.architecture_and_system_design)
    assert out in {
        "It shapes the trade-offs I make when designing system boundaries and keeping services operable over time.",
        "It affects long-term complexity and operability when scaling systems.",
    }


def test_synthesize_answer_includes_style_and_why_hints_and_parses_indices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict[str, object] = {}
    payload = {
        "answer": "Some sufficiently long answer that is not a refusal.",
        "why_this_matters": "Because.",
        "confidence": "Medium",
        "confidence_reason": None,
        "used_chunk_indices": ["0", "x", "0"],
    }
    monkeypatch.setattr(llm, "get_settings", lambda: _settings())
    monkeypatch.setattr("app.openai_client.get_settings", lambda: _settings())
    monkeypatch.setattr("app.openai_client._client", None)
    monkeypatch.setattr(
        "app.openai_client.OpenAI",
        lambda api_key: _FakeOpenAI(content=json.dumps(payload), capture=capture),
    )

    chunks = [
        RetrievedChunk(
            card_id="c1",
            category="cat",
            section="Overview",
            source_url=None,
            content="Evidence sentence one. Evidence sentence two.",
            distance=0.1,
        )
    ]
    result = llm.synthesize_answer(
        "q", chunks, category=Category.hands_on_engineering.value
    )
    assert result.used_chunk_indices == [0]

    user_msg = capture["kwargs"]["messages"][1]["content"]  # type: ignore[index]
    assert "Answer style hint:" in user_msg
    assert "Why-this-matters hint:" in user_msg


def test_parse_category_debug_branch_and_generic_fallbacks(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")
    llm.logger.setLevel("DEBUG")

    assert llm._parse_category("???").value == Category.hands_on_engineering.value
    assert any("unknown_category_string" in r.message for r in caplog.records)

    assert llm._stable_choice((), seed="x") == ""
    generic = {
        "It affects how I make technical decisions.",
        "It influences practical trade-offs I make when building systems.",
    }
    assert llm._fallback_why(category=None, seed="s") in generic
    assert llm.clean_why("It demonstrates.", category="Unknown") in generic


def test_route_categories_parses_multi_category_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm, "get_settings", lambda: _settings())

    class _Resp:
        class _Msg:
            def __init__(self, content: str) -> None:
                self.content = content

        class _Choice:
            def __init__(self, content: str) -> None:
                self.message = _Resp._Msg(content)

        def __init__(self, content: str) -> None:
            self.choices = [_Resp._Choice(content)]

    payload = {
        "categories": [
            {
                "category": Category.education_and_formal_background.value,
                "confidence": "High",
                "budget": 2,
            },
            {
                "category": Category.hands_on_engineering.value,
                "confidence": "Medium",
                "budget": 3,
            },
        ]
    }

    monkeypatch.setattr(
        llm,
        "chat_completions_create_cached",
        lambda **kwargs: _Resp(json.dumps(payload)),
    )

    out = llm.route_categories("q")
    assert len(out.categories) == 2
    assert out.categories[0].category == Category.education_and_formal_background
    assert out.categories[0].confidence == Confidence.high
    assert out.categories[0].budget == 2
    assert out.categories[1].category == Category.hands_on_engineering
    assert out.categories[1].confidence == Confidence.medium
    assert out.categories[1].budget == 3


def test_route_categories_rejects_unknown_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm, "get_settings", lambda: _settings())

    class _Resp:
        class _Msg:
            def __init__(self, content: str) -> None:
                self.content = content

        class _Choice:
            def __init__(self, content: str) -> None:
                self.message = _Resp._Msg(content)

        def __init__(self, content: str) -> None:
            self.choices = [_Resp._Choice(content)]

    payload = {
        "categories": [
            {
                "category": "Not a real category",
                "confidence": "High",
                "budget": 2,
            }
        ]
    }

    monkeypatch.setattr(
        llm,
        "chat_completions_create_cached",
        lambda **kwargs: _Resp(json.dumps(payload)),
    )

    with pytest.raises(ValueError):
        llm.route_categories("q")
