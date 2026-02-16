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
from app.routing_category import RoutingCategory
from app.schemas import Confidence


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
            card_category="cat",
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
            card_category="cat",
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
            card_category="cat",
            section="Overview",
            source_url=None,
            content="One. Two.",
            distance=0.1,
        ),
        RetrievedChunk(
            card_id="c2",
            card_category="cat",
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
    out = llm.clean_why(text, RoutingCategory.hands_on_engineering)
    assert "highlights" not in out.lower()
    assert "reliability" in out.lower()


def test_clean_why_uses_category_specific_fallback_when_too_short() -> None:
    out = llm.clean_why(
        "It demonstrates.", RoutingCategory.education_and_formal_background
    )
    assert out in {
        "It gives a foundation I rely on when reasoning about systems and data.",
        "It provides background that shapes how I approach technical problems.",
    }


def test_clean_why_empty_returns_category_specific_fallback() -> None:
    out = llm.clean_why(" ", RoutingCategory.architecture_and_system_design)
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
            card_category="cat",
            section="Overview",
            source_url=None,
            content="Evidence sentence one. Evidence sentence two.",
            distance=0.1,
        )
    ]
    result = llm.synthesize_answer(
        "q", chunks, routing_category=RoutingCategory.hands_on_engineering.value
    )
    assert result.used_chunk_indices == [0]

    user_msg = capture["kwargs"]["messages"][1]["content"]  # type: ignore[index]
    assert "Answer style hint:" in user_msg
    assert "Why-this-matters hint:" in user_msg


def test_parse_routing_category_debug_branch_and_generic_fallbacks(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")
    llm.logger.setLevel("DEBUG")

    assert (
        llm._parse_routing_category("???").value
        == RoutingCategory.hands_on_engineering.value
    )
    assert any("unknown_routing_category_string" in r.message for r in caplog.records)

    assert llm._stable_choice((), seed="x") == ""
    generic = {
        "It affects how I make technical decisions.",
        "It influences practical trade-offs I make when building systems.",
    }
    assert llm._fallback_why(routing_category=None, seed="s") in generic
    assert llm.clean_why("It demonstrates.", routing_category="Unknown") in generic


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
        "routing_categories": [
            {
                "routing_category": RoutingCategory.education_and_formal_background.value,
                "confidence": "High",
                "budget": 2,
            },
            {
                "routing_category": RoutingCategory.hands_on_engineering.value,
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
    assert len(out.routing_categories) == 2
    assert (
        out.routing_categories[0].routing_category
        == RoutingCategory.education_and_formal_background
    )
    assert out.routing_categories[0].confidence == Confidence.high
    assert out.routing_categories[0].budget == 2
    assert (
        out.routing_categories[1].routing_category
        == RoutingCategory.hands_on_engineering
    )
    assert out.routing_categories[1].confidence == Confidence.medium
    assert out.routing_categories[1].budget == 3


def test_route_categories_rejects_unknown_routing_category(
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
        "routing_categories": [
            {
                "routing_category": "Not a real category",
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


def test_route_categories_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that route_categories raises RuntimeError without API key."""
    monkeypatch.setattr(llm, "get_settings", lambda: _settings(openai_api_key=None))
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        llm.route_categories("q")


def test_route_category_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that route_category raises RuntimeError without API key."""
    monkeypatch.setattr(llm, "get_settings", lambda: _settings(openai_api_key=None))
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        llm.route_category("q")


def test_route_categories_accepts_legacy_categories_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that route_categories accepts legacy 'categories' key."""
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

    # Use legacy 'categories' key instead of 'routing_categories'
    payload = {
        "categories": [
            {
                "category": RoutingCategory.education_and_formal_background.value,
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

    out = llm.route_categories("q")
    assert len(out.routing_categories) == 1
    assert (
        out.routing_categories[0].routing_category
        == RoutingCategory.education_and_formal_background
    )


def test_route_categories_rejects_empty_categories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that route_categories raises ValueError for empty categories."""
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

    monkeypatch.setattr(
        llm,
        "chat_completions_create_cached",
        lambda **kwargs: _Resp(json.dumps({"routing_categories": []})),
    )

    with pytest.raises(ValueError, match="no categories"):
        llm.route_categories("q")


def test_route_categories_skips_non_dict_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that route_categories skips non-dict items in the list."""
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
        "routing_categories": [
            "not a dict",
            {
                "routing_category": RoutingCategory.hands_on_engineering.value,
                "confidence": "High",
                "budget": 2,
            },
        ]
    }

    monkeypatch.setattr(
        llm,
        "chat_completions_create_cached",
        lambda **kwargs: _Resp(json.dumps(payload)),
    )

    out = llm.route_categories("q")
    assert len(out.routing_categories) == 1


def test_route_categories_handles_invalid_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that route_categories handles invalid budget values."""
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
        "routing_categories": [
            {
                "routing_category": RoutingCategory.hands_on_engineering.value,
                "confidence": "High",
                "budget": "not-an-int",
            }
        ]
    }

    monkeypatch.setattr(
        llm,
        "chat_completions_create_cached",
        lambda **kwargs: _Resp(json.dumps(payload)),
    )

    out = llm.route_categories("q")
    assert out.routing_categories[0].budget is None


def test_route_categories_no_valid_items_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that route_categories raises when all items are invalid."""
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

    # All items are non-dict
    payload = {"routing_categories": ["not a dict", "also not a dict"]}

    monkeypatch.setattr(
        llm,
        "chat_completions_create_cached",
        lambda **kwargs: _Resp(json.dumps(payload)),
    )

    with pytest.raises(ValueError, match="no valid routing_categories"):
        llm.route_categories("q")


def test_synthesize_answer_multi_category_evidence_grouping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test multi-category evidence grouping in synthesize_answer."""
    capture: dict[str, object] = {}
    payload = {
        "answer": "Some sufficiently long answer that is not a refusal.",
        "why_this_matters": "Because.",
        "confidence": "Medium",
        "confidence_reason": None,
        "used_chunk_indices": [0, 1],
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
            card_category="cat",
            section="Overview",
            source_url=None,
            content="Evidence one.",
            distance=0.1,
        ),
        RetrievedChunk(
            card_id="c2",
            card_category="cat",
            section="Details",
            source_url=None,
            content="Evidence two.",
            distance=0.2,
        ),
    ]

    # Add origin_routing_category attribute
    chunks[0].origin_routing_category = RoutingCategory.education_and_formal_background  # type: ignore[attr-defined]
    chunks[1].origin_routing_category = RoutingCategory.hands_on_engineering  # type: ignore[attr-defined]

    routing = llm.RoutingResult(
        routing_categories=[
            llm.RoutedCategory(
                routing_category=RoutingCategory.education_and_formal_background,
                confidence=Confidence.high,
                budget=2,
            ),
            llm.RoutedCategory(
                routing_category=RoutingCategory.hands_on_engineering,
                confidence=Confidence.medium,
                budget=3,
            ),
        ]
    )

    result = llm.synthesize_answer("q", chunks, routing=routing)
    assert result.used_chunk_indices == [0, 1]

    # Check that evidence was grouped
    user_msg = capture["kwargs"]["messages"][1]["content"]  # type: ignore[index]
    assert "Evidence groups" in user_msg


def test_synthesize_answer_strict_facts_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test strict_facts_first mode adds extra instructions."""
    capture: dict[str, object] = {}
    payload = {
        "answer": "Some sufficiently long answer that is not a refusal.",
        "why_this_matters": "Because.",
        "confidence": "Medium",
        "confidence_reason": None,
        "used_chunk_indices": [0],
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
            card_category="cat",
            section="Overview",
            source_url=None,
            content="Evidence one.",
            distance=0.1,
        )
    ]

    result = llm.synthesize_answer("q", chunks, strict_facts_first=True)
    assert result.answer

    system_msg = capture["kwargs"]["messages"][0]["content"]  # type: ignore[index]
    assert "STRICT MODE" in system_msg


def test_synthesize_answer_too_short_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that too-short answers fall back to deterministic synthesis."""
    payload = {
        "answer": "Yes",  # Too short
        "why_this_matters": "Because.",
        "confidence": "High",
        "confidence_reason": None,
        "used_chunk_indices": [0],
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
            card_category="cat",
            section="Overview",
            source_url=None,
            content="Evidence sentence one. Evidence sentence two.",
            distance=0.1,
        )
    ]

    result = llm.synthesize_answer("q", chunks)
    # Should fall back to deterministic synthesis
    assert "Evidence sentence" in result.answer


def test_synthesize_answer_no_api_key_uses_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that synthesize_answer uses fallback when no API key."""
    monkeypatch.setattr(llm, "get_settings", lambda: _settings(openai_api_key=None))

    chunks = [
        RetrievedChunk(
            card_id="c1",
            card_category="cat",
            section="Overview",
            source_url=None,
            content="Evidence sentence one. Evidence sentence two.",
            distance=0.1,
        )
    ]

    result = llm.synthesize_answer("q", chunks)
    assert "Evidence sentence" in result.answer
    assert result.confidence == Confidence.medium


def test_fallback_synthesis_empty_sentences_uses_first_chunk() -> None:
    """Test _fallback_synthesis with empty sentences uses first chunk content."""
    chunks = [
        RetrievedChunk(
            card_id="c1",
            card_category="cat",
            section="Overview",
            source_url=None,
            content="Single content without sentence ending",
            distance=0.1,
        )
    ]

    result = llm._fallback_synthesis(chunks)
    assert result.answer == "Single content without sentence ending"
    assert result.used_chunk_indices == [0]


def test_synthesize_answer_with_temperature_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that temperature_override is passed to the API."""
    capture: dict[str, object] = {}
    payload = {
        "answer": "Some sufficiently long answer that is not a refusal.",
        "why_this_matters": "Because.",
        "confidence": "Medium",
        "confidence_reason": None,
        "used_chunk_indices": [0],
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
            card_category="cat",
            section="Overview",
            source_url=None,
            content="Evidence one.",
            distance=0.1,
        )
    ]

    result = llm.synthesize_answer("q", chunks, temperature_override=0.5)
    assert result.answer
    assert capture["kwargs"]["temperature"] == 0.5


def test_clean_why_with_prefix_patterns() -> None:
    """Test clean_why removes common prefix patterns."""
    # Test "It is important to note that" removal
    result = llm.clean_why("It is important to note that this matters.")
    assert "important to note" not in result.lower()

    # Test "This demonstrates" removal
    result = llm.clean_why("This demonstrates the value.", RoutingCategory.hands_on_engineering)
    # Should fall back because result is too short after removal
    assert result in {
        "It affects how I build and debug production systems.",
        "It influences the trade-offs I make around reliability, maintainability, and delivery.",
    }


def test_clean_why_removes_to_prefix() -> None:
    """Test clean_why removes 'to ' prefix artifacts."""
    result = llm.clean_why("to build better systems we need good practices", RoutingCategory.hands_on_engineering)
    # After removing "to " prefix, should still be valid or fall back
    assert result  # Should return something


def test_parse_confidence_edge_cases() -> None:
    """Test _parse_confidence with various inputs."""
    assert llm._parse_confidence("HIGH") == Confidence.high
    assert llm._parse_confidence("  high  ") == Confidence.high
    assert llm._parse_confidence("low") == Confidence.low
    assert llm._parse_confidence("medium") == Confidence.medium
    assert llm._parse_confidence("unknown") == Confidence.medium
    assert llm._parse_confidence("") == Confidence.medium


def test_route_category_parses_with_legacy_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test route_category accepts legacy 'category' key."""
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

    # Use legacy 'category' key
    payload = {"category": RoutingCategory.hands_on_engineering.value}

    monkeypatch.setattr(
        llm,
        "chat_completions_create_cached",
        lambda **kwargs: _Resp(json.dumps(payload)),
    )

    result = llm.route_category("q")
    assert result == RoutingCategory.hands_on_engineering


def test_rewrite_question_returns_original_when_no_messages() -> None:
    """Test rewrite_question returns original when messages is None or empty."""
    assert llm.rewrite_question("q", messages=None) == "q"
    assert llm.rewrite_question("q", messages=[]) == "q"


def test_rewrite_question_returns_original_when_no_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test rewrite_question returns original when no API key."""
    monkeypatch.setattr(llm, "get_settings", lambda: _settings(openai_api_key=None))
    assert llm.rewrite_question("q", messages=[{"role": "user", "content": "x"}]) == "q"
