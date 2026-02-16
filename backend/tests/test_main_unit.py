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
# Unit tests for small helpers and middleware error path in main.

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import BackgroundTasks
from starlette.requests import Request

from app.llm import SynthesisResult
from app.main import _is_uuid, chat, classify_question, request_logging_middleware
from app.retrieval import RetrievedChunk
from app.routing_category import RoutingCategory
from app.schemas import (
    ChatMessage,
    ChatRequest,
    Confidence,
    ConversationContext,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        ("not-a-uuid", False),
        ("00000000-0000-0000-0000-000000000000", True),
    ],
)
def test_is_uuid(value: str | None, expected: bool) -> None:
    assert _is_uuid(value) is expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "Tell me about your team strategy",
            RoutingCategory.leadership_and_product_strategy,
        ),
        (
            "Discuss system architecture",
            RoutingCategory.architecture_and_system_design,
        ),
        ("AI embedding models?", RoutingCategory.ai_and_ml_practice),
        ("Any publication paper?", RoutingCategory.research_and_academic_credibility),
        (
            "Are you a good fit for this position?",
            RoutingCategory.career_fit_and_role_alignment,
        ),
        ("What did you build?", RoutingCategory.hands_on_engineering),
    ],
)
def test_classify_question_branches(question: str, expected: RoutingCategory) -> None:
    assert classify_question(question) == expected


@pytest.mark.anyio
async def test_request_logging_middleware_logs_and_reraises_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, Any] = {"reset": 0}

    monkeypatch.setattr("app.main.set_request_id", lambda rid: "token")
    monkeypatch.setattr(
        "app.main.reset_request_id",
        lambda token: called.__setitem__("reset", called["reset"] + 1),
    )

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/boom",
        "headers": [],
        "client": ("203.0.113.10", 1234),
    }
    request = Request(scope)

    async def _call_next(req: Request):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await request_logging_middleware(request, _call_next)

    assert called["reset"] == 1


def _make_http_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/chat",
        "headers": [],
        "client": ("203.0.113.10", 1234),
    }
    req = Request(scope)
    req.state.session_id = "00000000-0000-0000-0000-000000000000"
    return req


def test_chat_does_not_use_last_topic_for_retrieval_when_messages_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _retrieve(
        question: str, limit: int = 25, conversation_topic: str | None = None
    ):
        captured["conversation_topic"] = conversation_topic
        return []

    monkeypatch.setattr("app.main.retrieve", _retrieve)
    monkeypatch.setattr("app.main.rewrite_question", lambda q, messages=None: q)
    monkeypatch.setattr(
        "app.main.route_category",
        lambda q: (_ for _ in ()).throw(RuntimeError("no router")),
    )
    monkeypatch.setattr(
        "app.main.synthesize_answer",
        lambda *args, **kwargs: SynthesisResult(
            answer="ok",
            why_this_matters="ok",
            confidence=Confidence.medium,
            confidence_reason=None,
            used_chunk_indices=[],
        ),
    )
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: SimpleNamespace(
            router_model="router",
            synthesis_model="synth",
            synthesis_temperature=0.1,
            embeddings_provider="stub",
            embeddings_model="stub",
            ip_hash_salt="salt",
            interaction_log_include_llm_context=True,
        ),
    )
    monkeypatch.setattr("app.main.extract_client_ip", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.main.write_interaction_log", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.main.get_request_id", lambda: "req-1")

    http_request = _make_http_request()
    chat_request = ChatRequest(
        question="What is your education?",
        messages=[],
        context=ConversationContext(conversation_id="c1", last_topic="poison-topic"),
    )

    chat(
        http_request=http_request,
        request=chat_request,
        background_tasks=BackgroundTasks(),
    )
    assert captured["conversation_topic"] is None


def test_chat_uses_last_topic_for_retrieval_on_followup_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _retrieve(
        question: str, limit: int = 25, conversation_topic: str | None = None
    ):
        captured["conversation_topic"] = conversation_topic
        return []

    monkeypatch.setattr("app.main.retrieve", _retrieve)
    monkeypatch.setattr("app.main.rewrite_question", lambda q, messages=None: q)
    monkeypatch.setattr(
        "app.main.route_category",
        lambda q: (_ for _ in ()).throw(RuntimeError("no router")),
    )
    monkeypatch.setattr(
        "app.main.synthesize_answer",
        lambda *args, **kwargs: SynthesisResult(
            answer="ok",
            why_this_matters="ok",
            confidence=Confidence.medium,
            confidence_reason=None,
            used_chunk_indices=[],
        ),
    )
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: SimpleNamespace(
            router_model="router",
            synthesis_model="synth",
            synthesis_temperature=0.1,
            embeddings_provider="stub",
            embeddings_model="stub",
            ip_hash_salt="salt",
            interaction_log_include_llm_context=True,
        ),
    )
    monkeypatch.setattr("app.main.extract_client_ip", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.main.write_interaction_log", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.main.get_request_id", lambda: "req-1")

    http_request = _make_http_request()
    chat_request = ChatRequest(
        question="What about that?",
        messages=[ChatMessage(role="user", content="Tell me about Decreen.")],
        context=ConversationContext(conversation_id="c1", last_topic="decreen"),
    )

    chat(
        http_request=http_request,
        request=chat_request,
        background_tasks=BackgroundTasks(),
    )
    assert captured["conversation_topic"] == "decreen"


@pytest.mark.parametrize(
    ("question", "expected_use_topic"),
    [
        ("and what about the scale?", True),
        ("Is it production-ready?", True),
        ("Why?", True),
        ("   ", False),
    ],
)
def test_chat_topic_heuristics_controls_retrieval_topic_usage(
    monkeypatch: pytest.MonkeyPatch, question: str, expected_use_topic: bool
) -> None:
    captured: dict[str, Any] = {}

    def _retrieve(q: str, limit: int = 25, conversation_topic: str | None = None):
        captured["conversation_topic"] = conversation_topic
        return []

    monkeypatch.setattr("app.main.retrieve", _retrieve)
    monkeypatch.setattr("app.main.rewrite_question", lambda q, messages=None: q)
    monkeypatch.setattr(
        "app.main.route_category",
        lambda q: (_ for _ in ()).throw(RuntimeError("no router")),
    )
    monkeypatch.setattr(
        "app.main.synthesize_answer",
        lambda *args, **kwargs: SynthesisResult(
            answer="ok",
            why_this_matters="ok",
            confidence=Confidence.medium,
            confidence_reason=None,
            used_chunk_indices=[],
        ),
    )
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: SimpleNamespace(
            router_model="router",
            synthesis_model="synth",
            synthesis_temperature=0.1,
            embeddings_provider="stub",
            embeddings_model="stub",
            ip_hash_salt="salt",
            interaction_log_include_llm_context=True,
        ),
    )
    monkeypatch.setattr("app.main.extract_client_ip", lambda *a, **k: None)
    monkeypatch.setattr("app.main.write_interaction_log", lambda *a, **k: None)
    monkeypatch.setattr("app.main.get_request_id", lambda: "req-1")

    http_request = _make_http_request()
    chat_request = ChatRequest(
        question=question,
        messages=[ChatMessage(role="user", content="prior")],
        context=ConversationContext(conversation_id="c1", last_topic="topic"),
    )
    chat(
        http_request=http_request,
        request=chat_request,
        background_tasks=BackgroundTasks(),
    )

    expected = "topic" if expected_use_topic else None
    assert captured["conversation_topic"] == expected


def test_chat_swallow_background_task_scheduling_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Cover the defensive `try/except` around scheduling background tasks.
    monkeypatch.setattr("app.main.retrieve", lambda *a, **k: [])
    monkeypatch.setattr("app.main.rewrite_question", lambda q, messages=None: q)
    monkeypatch.setattr(
        "app.main.route_category",
        lambda q: (_ for _ in ()).throw(RuntimeError("no router")),
    )
    monkeypatch.setattr(
        "app.main.synthesize_answer",
        lambda *args, **kwargs: SynthesisResult(
            answer="ok",
            why_this_matters="ok",
            confidence=Confidence.medium,
            confidence_reason=None,
            used_chunk_indices=[],
        ),
    )
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: SimpleNamespace(
            router_model="router",
            synthesis_model="synth",
            synthesis_temperature=0.1,
            embeddings_provider="stub",
            embeddings_model="stub",
            ip_hash_salt="salt",
            interaction_log_include_llm_context=True,
        ),
    )
    monkeypatch.setattr("app.main.extract_client_ip", lambda *a, **k: None)
    monkeypatch.setattr("app.main.get_request_id", lambda: "req-1")

    http_request = _make_http_request()
    chat_request = ChatRequest(question="Q", messages=[], context=None)

    response = chat(
        http_request=http_request,
        request=chat_request,
        background_tasks=object(),
    )
    assert response.answer == "ok"


def test_chat_multi_category_routes_on_original_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "app.main.rewrite_question", lambda q, messages=None: "REWRITTEN"
    )

    def _route_categories(q: str):
        captured["routing_input"] = q
        return SimpleNamespace(
            routing_categories=[
                SimpleNamespace(
                    routing_category=RoutingCategory.education_and_formal_background,
                    confidence=Confidence.high,
                    budget=None,
                ),
                SimpleNamespace(
                    routing_category=RoutingCategory.hands_on_engineering,
                    confidence=Confidence.medium,
                    budget=None,
                ),
            ]
        )

    monkeypatch.setattr("app.main.route_categories", _route_categories)

    calls: list[tuple[str, int]] = []

    def _retrieve_for_category(
        question: str,
        *,
        routing_category: str,
        budget: int,
        conversation_topic: str | None = None,
        section_weights: dict[str, float] | None = None,
    ):
        calls.append((routing_category, budget))
        return [
            RetrievedChunk(
                card_id=f"{routing_category}-card",
                card_category="cat",
                section="Overview",
                source_url=None,
                content=f"chunk for {routing_category}",
                distance=0.10,
                origin_routing_categories=[routing_category],
                origin_routing_category=routing_category,
                pinned=False,
            )
        ]

    monkeypatch.setattr("app.main.retrieve_for_category", _retrieve_for_category)

    monkeypatch.setattr(
        "app.main.synthesize_answer",
        lambda *a, **k: SynthesisResult(
            answer="ok",
            why_this_matters="ok",
            confidence=Confidence.medium,
            confidence_reason=None,
            used_chunk_indices=[0],
        ),
    )

    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: SimpleNamespace(
            router_model="router",
            synthesis_model="synth",
            synthesis_temperature=0.1,
            embeddings_provider="stub",
            embeddings_model="stub",
            ip_hash_salt="salt",
            interaction_log_include_llm_context=True,
            retrieval_per_card_cap=2,
            multi_category_retrieval_enabled=True,
            multi_category_rollout_percent=100,
            multi_category_max_categories=2,
            multi_category_max_total_chunks=5,
            multi_category_allow_six_chunks=False,
            multi_category_intent_budget_policy="intent_rules_v1",
            multi_category_pinning_rules={},
            multi_category_section_weights={},
        ),
    )
    monkeypatch.setattr("app.main.extract_client_ip", lambda *a, **k: None)
    monkeypatch.setattr("app.main.write_interaction_log", lambda *a, **k: None)
    monkeypatch.setattr("app.main.get_request_id", lambda: "req-1")

    http_request = _make_http_request()
    chat_request = ChatRequest(
        question="What is your educational background, and how has it shaped your career?",
        messages=[],
        context=ConversationContext(conversation_id="c1", last_topic=None),
    )

    response = chat(
        http_request=http_request,
        request=chat_request,
        background_tasks=BackgroundTasks(),
        debug_retrieval=True,
    )

    assert captured["routing_input"] == chat_request.question
    assert response.routing is not None
    assert calls, "Expected per-category retrieval calls"


def test_chat_multi_category_empty_pinning_rules_no_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: empty pinning rules should not change retrieval behavior.

    When multi_category_pinning_rules is an empty dict, the multi-category flow
    should complete successfully and retrieve_for_card should NOT be called.
    """
    captured: dict[str, object] = {}
    retrieve_for_card_calls: list[tuple[str, int]] = []

    monkeypatch.setattr(
        "app.main.rewrite_question", lambda q, messages=None: "REWRITTEN"
    )

    def _route_categories(q: str):
        captured["routing_input"] = q
        return SimpleNamespace(
            routing_categories=[
                SimpleNamespace(
                    routing_category=RoutingCategory.education_and_formal_background,
                    confidence=Confidence.high,
                    budget=None,
                ),
                SimpleNamespace(
                    routing_category=RoutingCategory.hands_on_engineering,
                    confidence=Confidence.medium,
                    budget=None,
                ),
            ]
        )

    monkeypatch.setattr("app.main.route_categories", _route_categories)

    calls: list[tuple[str, int]] = []

    def _retrieve_for_category(
        question: str,
        *,
        routing_category: str,
        budget: int,
        conversation_topic: str | None = None,
        section_weights: dict[str, float] | None = None,
    ):
        calls.append((routing_category, budget))
        return [
            RetrievedChunk(
                card_id=f"{routing_category}-card",
                card_category="cat",
                section="Overview",
                source_url=None,
                content=f"chunk for {routing_category}",
                distance=0.10,
                origin_routing_categories=[routing_category],
                origin_routing_category=routing_category,
                pinned=False,
            )
        ]

    monkeypatch.setattr("app.main.retrieve_for_category", _retrieve_for_category)

    # Mock retrieve_for_card to track if it's called (it should NOT be called)
    def _retrieve_for_card(
        question: str,
        *,
        card_id: str,
        limit: int,
        origin_routing_category: str = "",
        conversation_topic: str | None = None,
    ):
        retrieve_for_card_calls.append((card_id, limit))
        return [
            RetrievedChunk(
                card_id=card_id,
                card_category="cat",
                section="Overview",
                source_url=None,
                content=f"pinned chunk for {card_id}",
                distance=0.05,
                origin_routing_categories=[origin_routing_category]
                if origin_routing_category
                else [],
                origin_routing_category=origin_routing_category
                if origin_routing_category
                else None,
                pinned=True,
            )
        ]

    monkeypatch.setattr("app.main.retrieve_for_card", _retrieve_for_card)

    monkeypatch.setattr(
        "app.main.synthesize_answer",
        lambda *a, **k: SynthesisResult(
            answer="ok",
            why_this_matters="ok",
            confidence=Confidence.medium,
            confidence_reason=None,
            used_chunk_indices=[0],
        ),
    )

    # Key: empty pinning rules
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: SimpleNamespace(
            router_model="router",
            synthesis_model="synth",
            synthesis_temperature=0.1,
            embeddings_provider="stub",
            embeddings_model="stub",
            ip_hash_salt="salt",
            interaction_log_include_llm_context=True,
            retrieval_per_card_cap=2,
            multi_category_retrieval_enabled=True,
            multi_category_rollout_percent=100,
            multi_category_max_categories=2,
            multi_category_max_total_chunks=5,
            multi_category_allow_six_chunks=False,
            multi_category_intent_budget_policy="intent_rules_v1",
            multi_category_pinning_rules={},  # EMPTY pinning rules
            multi_category_section_weights={},  # EMPTY section weights
        ),
    )
    monkeypatch.setattr("app.main.extract_client_ip", lambda *a, **k: None)
    monkeypatch.setattr("app.main.write_interaction_log", lambda *a, **k: None)
    monkeypatch.setattr("app.main.get_request_id", lambda: "req-1")

    http_request = _make_http_request()
    chat_request = ChatRequest(
        question="What is your educational background, and how has it shaped your career?",
        messages=[],
        context=ConversationContext(conversation_id="c1", last_topic=None),
    )

    response = chat(
        http_request=http_request,
        request=chat_request,
        background_tasks=BackgroundTasks(),
        debug_retrieval=True,
    )

    # Verify the flow completed successfully
    assert captured["routing_input"] == chat_request.question
    assert response.routing is not None
    assert calls, "Expected per-category retrieval calls"

    # Key assertion: retrieve_for_card should NOT be called when pinning rules are empty
    assert retrieve_for_card_calls == [], (
        f"retrieve_for_card should not be called with empty pinning rules, but got: {retrieve_for_card_calls}"
    )


def test_chat_multi_category_enforces_coverage_after_synthesis_omits_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: multi-category coverage is enforced even when synthesis omits a category.

    This test verifies that when:
    1. Routing returns 2 categories
    2. Synthesis returns used_chunk_indices only from category #1

    The pipeline forces inclusion of at least one chunk from the missing category
    so the final response evidence includes chunks from both categories.
    """
    captured: dict[str, object] = {}
    synthesis_call_count: list[int] = [0]

    monkeypatch.setattr(
        "app.main.rewrite_question", lambda q, messages=None: "REWRITTEN"
    )

    def _route_categories(q: str):
        captured["routing_input"] = q
        return SimpleNamespace(
            routing_categories=[
                SimpleNamespace(
                    routing_category=RoutingCategory.education_and_formal_background,
                    confidence=Confidence.high,
                    budget=None,
                ),
                SimpleNamespace(
                    routing_category=RoutingCategory.hands_on_engineering,
                    confidence=Confidence.medium,
                    budget=None,
                ),
            ]
        )

    monkeypatch.setattr("app.main.route_categories", _route_categories)

    def _retrieve_for_category(
        question: str,
        *,
        routing_category: str,
        budget: int,
        conversation_topic: str | None = None,
        section_weights: dict[str, float] | None = None,
    ):
        return [
            RetrievedChunk(
                card_id=f"{routing_category}-card",
                card_category="cat",
                section="Overview",
                source_url=None,
                content=f"chunk for {routing_category}",
                distance=0.10,
                origin_routing_categories=[routing_category],
                origin_routing_category=routing_category,
                pinned=False,
            )
        ]

    monkeypatch.setattr("app.main.retrieve_for_category", _retrieve_for_category)

    def _synthesize_answer(
        question: str,
        chunks: list[RetrievedChunk],
        routing_category,
        conversation_topic: str | None = None,
        conversation_messages: list[dict] | None = None,
        routing=None,
        **kwargs,
    ):
        synthesis_call_count[0] += 1
        # First call: only use chunk from first category (index 0)
        # This simulates the bug where synthesis ignores the second category
        if synthesis_call_count[0] == 1:
            return SynthesisResult(
                answer="Answer only from education category.",
                why_this_matters="Test why.",
                confidence=Confidence.medium,
                confidence_reason=None,
                used_chunk_indices=[0],  # Only first category chunk
            )
        # Retry call: still only use first category (simulates persistent bug)
        return SynthesisResult(
            answer="Answer still only from education category.",
            why_this_matters="Test why.",
            confidence=Confidence.medium,
            confidence_reason=None,
            used_chunk_indices=[0],  # Still only first category chunk
        )

    monkeypatch.setattr("app.main.synthesize_answer", _synthesize_answer)

    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: SimpleNamespace(
            router_model="router",
            synthesis_model="synth",
            synthesis_temperature=0.1,
            embeddings_provider="stub",
            embeddings_model="stub",
            ip_hash_salt="salt",
            interaction_log_include_llm_context=True,
            retrieval_per_card_cap=2,
            multi_category_retrieval_enabled=True,
            multi_category_rollout_percent=100,
            multi_category_max_categories=2,
            multi_category_max_total_chunks=5,
            multi_category_allow_six_chunks=False,
            multi_category_intent_budget_policy="intent_rules_v1",
            multi_category_pinning_rules={},
            multi_category_section_weights={},
        ),
    )
    monkeypatch.setattr("app.main.extract_client_ip", lambda *a, **k: None)
    monkeypatch.setattr("app.main.write_interaction_log", lambda *a, **k: None)
    monkeypatch.setattr("app.main.get_request_id", lambda: "req-1")

    http_request = _make_http_request()
    chat_request = ChatRequest(
        question="What is your educational background and hands-on experience?",
        messages=[],
        context=ConversationContext(conversation_id="c1", last_topic=None),
    )

    response = chat(
        http_request=http_request,
        request=chat_request,
        background_tasks=BackgroundTasks(),
        debug_retrieval=True,
    )

    # Key assertion: evidence must include chunks from BOTH categories
    # even though synthesis only returned chunks from the first category
    evidence_card_ids = [e.card_id for e in response.evidence]

    # Both category cards should be present in evidence
    assert "Education and formal background-card" in evidence_card_ids, (
        f"Expected education category in evidence, got: {evidence_card_ids}"
    )
    assert "Hands-on engineering-card" in evidence_card_ids, (
        f"Expected hands-on engineering category in evidence, got: {evidence_card_ids}"
    )

    # Verify we have evidence from both categories
    assert len(response.evidence) >= 2, (
        f"Expected at least 2 evidence items (one from each category), got: {len(response.evidence)}"
    )
