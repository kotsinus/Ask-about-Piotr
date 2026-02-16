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
# Defines the /chat API endpoint and request orchestration logic.
#
# Notes:
# This module enforces the strict answer contract defined in schemas.py.

from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from datetime import UTC, datetime

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import APIConnectionError, APIError, AuthenticationError, RateLimitError

from app.config import get_settings, get_web_settings
from app.geoip import lookup_country
from app.interaction_logging import InteractionLog, write_interaction_log
from app.llm import (
    RoutedCategory,
    RoutingResult,
    SynthesisResult,
    clean_why,
    rewrite_question,
    route_categories,
    route_category,
    synthesize_answer,
)
from app.logging_setup import configure_logging
from app.observability import (
    REQUEST_ID_HEADER,
    get_request_id,
    reset_request_id,
    set_request_id,
)
from app.privacy import anonymize_ip_prefix, extract_client_ip, hash_ip
from app.quality import validate_answer_quality
from app.retrieval import (
    apply_pinning,
    cap_chunks_with_coverage,
    merge_dedup_preserve_provenance,
    retrieve,
    retrieve_for_card,
    retrieve_for_category,
)
from app.routing_category import RoutingCategory
from app.schemas import (
    ChatRequest,
    ChatResponse,
    Confidence,
    ConversationContext,
    DebugRetrievalItem,
    EvidenceItem,
    RoutingCategoryAllocation,
    RoutingDebug,
    SourceRef,
)

configure_logging()

logger = logging.getLogger(__name__)

app = FastAPI(title="Ask about Piotr API", version="0.1.0")

# NOTE: we read web settings once at import time for middleware configuration.
# This must not depend on DATABASE_URL (tests import the app without a DB).
# If you need per-request overrides, rework this into an app factory.
_WEB_SETTINGS = get_web_settings()

SESSION_COOKIE_NAME = "ask_piotr_session_id"
SESSION_ID_HEADER = "x-session-id"


def _truncate_text(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    return value[:max_chars]


def _build_llm_context_messages(
    messages: list[dict] | None,
    *,
    max_messages: int = 6,
    max_content_chars: int = 2000,
) -> list[dict] | None:
    """Serialize the exact message window used as LLM context today.

    NOTE: The LLM prompt builders (rewrite + synthesis) currently trim to the
    last 6 messages. This helper mirrors that behavior so interaction logging can
    store what was actually passed.
    """

    if not messages:
        return None

    trimmed = messages[-max_messages:]
    payload: list[dict] = []
    for message in trimmed:
        role = str(message.get("role", "")).strip()
        content = str(message.get("content", ""))
        payload.append(
            {
                "role": role,
                "content": _truncate_text(content, max_content_chars),
            }
        )
    return payload


def _log_interaction_background(
    *,
    settings,
    request_id: str,
    session_id: str | None,
    conversation_id: str | None,
    request_at: datetime,
    response_at: datetime,
    latency_ms: float | None,
    question: str,
    standalone_question: str | None,
    answer: str,
    router_model: str | None,
    synthesis_model: str | None,
    embeddings_provider: str | None,
    embeddings_model: str | None,
    incoming_last_topic: str | None,
    resolved_topic: str | None,
    topic_used_for_retrieval: bool | None,
    messages_count: int | None,
    retrieval_chunk_count: int | None,
    llm_context_messages: list[dict] | None,
    client_ip: str | None,
    user_agent: str | None,
    # Multi-category routing diagnostics
    routing: dict | None = None,
    retrieval_by_category: dict | None = None,
    quality_gate: dict | None = None,
) -> None:
    """Best-effort interaction logging.

    This must never block the response path. We therefore run it as a
    background task (DB write + optional GeoIP HTTP call).
    """

    try:
        ip_prefix = anonymize_ip_prefix(client_ip) if client_ip else None
        ip_hash = None
        if client_ip and (settings.ip_hash_salt or "").strip():
            ip_hash = hash_ip(ip=client_ip, salt=settings.ip_hash_salt)
        country = lookup_country(client_ip, settings) if client_ip else None

        write_interaction_log(
            InteractionLog(
                request_id=request_id,
                session_id=session_id,
                conversation_id=conversation_id,
                request_at=request_at,
                response_at=response_at,
                latency_ms=latency_ms,
                question=question,
                standalone_question=standalone_question,
                answer=answer,
                router_model=router_model,
                synthesis_model=synthesis_model,
                embeddings_provider=embeddings_provider,
                embeddings_model=embeddings_model,
                incoming_last_topic=incoming_last_topic,
                resolved_topic=resolved_topic,
                topic_used_for_retrieval=topic_used_for_retrieval,
                messages_count=messages_count,
                retrieval_chunk_count=retrieval_chunk_count,
                llm_context_messages=llm_context_messages
                if settings.interaction_log_include_llm_context
                else None,
                ip_prefix=ip_prefix,
                ip_hash=ip_hash,
                user_agent=user_agent,
                country=country,
                # Multi-category routing diagnostics
                routing=routing,
                retrieval_by_category=retrieval_by_category,
                quality_gate=quality_gate,
            )
        )
    except Exception:
        logger.exception("interaction_log_failed")


def _is_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


app.add_middleware(
    CORSMiddleware,
    allow_origins=_WEB_SETTINGS.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    token = set_request_id(request_id)

    # Privacy-friendly anonymous session id.
    # - Stored as an HttpOnly cookie so the browser can keep a stable session.
    # - Not derived from IP.
    existing_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    header_session_id = request.headers.get(SESSION_ID_HEADER)

    session_id = (
        existing_session_id
        if _is_uuid(existing_session_id)
        else header_session_id
        if _is_uuid(header_session_id)
        else str(uuid.uuid4())
    )
    request.state.session_id = session_id

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.exception(
            "request_failed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "duration_ms": duration_ms,
            },
        )
        raise
    else:
        if not existing_session_id:
            secure_cookie = _WEB_SETTINGS.cookie_secure
            response.set_cookie(
                key=SESSION_COOKIE_NAME,
                value=session_id,
                httponly=True,
                samesite="lax",
                secure=secure_cookie,
                max_age=60 * 60 * 24 * 365,
            )
        response.headers[REQUEST_ID_HEADER] = request_id
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
    finally:
        reset_request_id(token)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(RateLimitError)
async def openai_rate_limit_handler(
    request: Request, exc: RateLimitError
) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "detail": "OpenAI rate limit exceeded. Please try again later.",
            "type": "rate_limit",
        },
    )


@app.exception_handler(AuthenticationError)
async def openai_auth_handler(
    request: Request, exc: AuthenticationError
) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "detail": "OpenAI authentication failed. Check OPENAI_API_KEY.",
            "type": "auth_error",
        },
    )


@app.exception_handler(APIConnectionError)
async def openai_connection_handler(
    request: Request, exc: APIConnectionError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": "OpenAI service is unavailable. Please try again later.",
            "type": "openai_unavailable",
        },
    )


@app.exception_handler(APIError)
async def openai_api_handler(request: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": "OpenAI service is unavailable. Please try again later.",
            "type": "openai_unavailable",
        },
    )


def classify_question(question: str) -> RoutingCategory:
    """Classify the question into exactly one routing category.

    TODO: Replace with a deterministic classifier or a small ruleset.
    """

    text = question.lower()
    if any(
        keyword in text
        for keyword in [
            "education",
            "educational",
            "degree",
            "phd",
            "m.sc",
            "msc",
            "master",
            "university",
            "academy",
        ]
    ):
        return RoutingCategory.education_and_formal_background
    if any(keyword in text for keyword in ["team", "lead", "strategy", "roadmap"]):
        return RoutingCategory.leadership_and_product_strategy
    if any(keyword in text for keyword in ["architecture", "design", "system"]):
        return RoutingCategory.architecture_and_system_design
    if any(keyword in text for keyword in ["ml", "ai", "model", "embedding"]):
        return RoutingCategory.ai_and_ml_practice
    if any(keyword in text for keyword in ["research", "paper", "publication"]):
        return RoutingCategory.research_and_academic_credibility
    if any(keyword in text for keyword in ["role", "fit", "position"]):
        return RoutingCategory.career_fit_and_role_alignment
    return RoutingCategory.hands_on_engineering


def _stable_request_percent(request_id: str) -> int:
    """Map request_id -> stable [0, 99] bucket."""

    if not request_id:
        return 0
    digest = hashlib.sha256(request_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % 100


def _multi_category_enabled(settings, request_id: str) -> bool:
    enabled = bool(getattr(settings, "multi_category_retrieval_enabled", False))
    if not enabled:
        return False
    rollout_percent = int(getattr(settings, "multi_category_rollout_percent", 0) or 0)
    rollout_percent = max(0, min(100, rollout_percent))
    if rollout_percent >= 100:
        return True
    if rollout_percent <= 0:
        return False
    return _stable_request_percent(request_id) < rollout_percent


def _confidence_rank(confidence: Confidence) -> int:
    if confidence == Confidence.high:
        return 2
    if confidence == Confidence.medium:
        return 1
    return 0


def _deterministic_budget_policy(
    *, question: str, categories: list[RoutedCategory], max_total_chunks: int
) -> list[int]:
    """Deterministic budget allocation based on confidence ranking.

    Returns budgets aligned with `categories` order.
    """

    budgets: list[int | None] = [None for _ in categories]

    if len(categories) == 1:
        return [max(1, max_total_chunks)]

    if len(categories) == 2:
        # Default total for 2 categories.
        total = max(2, max_total_chunks)

        # Deterministic default: give 3 to the higher-confidence category,
        # tie-break on category name.
        left, right = categories
        if _confidence_rank(left.confidence) > _confidence_rank(right.confidence):
            budgets[0], budgets[1] = 3, total - 3
        elif _confidence_rank(left.confidence) < _confidence_rank(right.confidence):
            budgets[0], budgets[1] = total - 3, 3
        else:
            if str(left.routing_category.value) <= str(right.routing_category.value):
                budgets[0], budgets[1] = 3, total - 3
            else:
                budgets[0], budgets[1] = total - 3, 3

        return [int(budgets[0] or 1), int(budgets[1] or 1)]

    # 3 categories: start with 2 each (total 6) then clamp later.
    return [2 for _ in categories]


def _clamp_budgets(
    *, categories: list[RoutedCategory], budgets: list[int], max_total_chunks: int
) -> list[int]:
    budgets = [max(1, int(b)) for b in budgets]
    max_total_chunks = max(1, int(max_total_chunks))

    def _score(idx: int) -> tuple[int, int, str]:
        # Lower score = reduce earlier.
        return (
            _confidence_rank(categories[idx].confidence),
            budgets[idx],
            str(categories[idx].routing_category.value),
        )

    while sum(budgets) > max_total_chunks:
        reducible = [i for i, b in enumerate(budgets) if b > 1]
        if not reducible:
            break
        # Reduce lowest confidence first; for ties, reduce larger budgets first.
        reducible_sorted = sorted(
            reducible,
            key=lambda i: (_score(i)[0], -_score(i)[1], _score(i)[2]),
        )
        budgets[reducible_sorted[0]] -= 1

    # Final safety: if still above cap due to pathological inputs, hard-trim.
    if sum(budgets) > max_total_chunks:
        budgets = budgets[:]
        budgets[-1] = max(1, budgets[-1] - (sum(budgets) - max_total_chunks))

    return budgets


def format_answer(
    answer: str,
    why_this_matters: str,
    evidence: list[EvidenceItem],
    sources: list[SourceRef],
    confidence: Confidence,
    confidence_reason: str | None,
) -> str:
    evidence_lines = (
        [f'- "{item.snippet}" ({item.card_id})' for item in evidence]
        if evidence
        else ["- None (no retrieved chunks)"]
    )
    source_lines = (
        [f"- {item.card_id}.{item.section}" for item in sources]
        if sources
        else ["- None"]
    )
    confidence_line = (
        f"{confidence.value} — {confidence_reason}"
        if confidence_reason and confidence == Confidence.low
        else confidence.value
    )

    return (
        "Answer:\n"
        f"{answer}\n\n"
        "Why this matters:\n"
        f"{why_this_matters}\n\n"
        "Evidence:\n" + "\n".join(evidence_lines) + "\n\n"
        "Sources:\n" + "\n".join(source_lines) + "\n\n"
        "Confidence:\n" + confidence_line
    )


@app.post("/chat", response_model=ChatResponse)
def chat(
    http_request: Request,
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    debug_retrieval: bool = False,
) -> ChatResponse:
    def _should_use_conversation_topic(question: str, messages_count: int) -> bool:
        """Heuristic: use topic only for follow-ups when we have history."""

        if messages_count <= 0:
            return False

        q = " ".join(question.strip().lower().split())
        if not q:
            return False

        followup_starts = (
            "and ",
            "also ",
            "what about",
            "how about",
        )
        if any(q.startswith(prefix) for prefix in followup_starts):
            return True

        # Ambiguity markers: third-person pronouns / deictic references.
        if re.search(r"\b(it|that|this|they|them|those|these)\b", q):
            return True

        # Very short questions without a clear addressee are often follow-ups.
        if len(q) <= 25 and not re.search(r"\b(you|your|piotr)\b", q):
            return True

        return False

    settings = get_settings()
    request_at = datetime.now(UTC)
    start = time.perf_counter()

    request_id = get_request_id() or ""
    session_id = getattr(http_request.state, "session_id", None)

    # If the client doesn't provide a conversation id, create one and return it
    # in the response context so the client can persist and reuse it.
    conversation_id = (
        request.context.conversation_id
        if request.context and request.context.conversation_id
        else str(uuid.uuid4())
    )

    messages_count = len(request.messages) if request.messages else 0
    incoming_last_topic = request.context.last_topic if request.context else None
    use_topic_for_retrieval = bool(
        incoming_last_topic
    ) and _should_use_conversation_topic(
        question=request.question,
        messages_count=messages_count,
    )
    conversation_topic = incoming_last_topic if use_topic_for_retrieval else None

    logger.info(
        "chat_start",
        extra={
            "session_id": session_id,
            "conversation_id": conversation_id,
            "messages_count": messages_count,
            "incoming_last_topic": incoming_last_topic,
            "topic_used_for_retrieval": use_topic_for_retrieval,
        },
    )

    # Stage timing logs (diagnostics): helps pinpoint hangs/timeouts without
    # logging raw user text.
    t_stage = time.perf_counter()

    logger.info(
        "chat_stage",
        extra={
            "stage": "rewrite_question_start",
            "messages_count": messages_count,
        },
    )
    standalone_question = rewrite_question(
        request.question,
        [message.model_dump() for message in request.messages]
        if request.messages
        else None,
    )
    logger.info(
        "chat_stage",
        extra={
            "stage": "rewrite_question_done",
            "duration_ms": round((time.perf_counter() - t_stage) * 1000, 2),
            "standalone_question_len": len(standalone_question or ""),
        },
    )
    t_stage = time.perf_counter()
    logger.info(
        "chat_stage",
        extra={
            "stage": "route_category_start",
        },
    )
    use_multi_category = _multi_category_enabled(settings, request_id)

    routing: RoutingResult | None = None
    router_fallback_used = False
    routing_category: RoutingCategory

    if use_multi_category:
        # IMPORTANT: route on the original user question (not rewritten).
        routing_question = request.question
        try:
            routing = route_categories(routing_question)
        except Exception:
            routing = None

        # Validate routing result minimally; any invalid output triggers fallback.
        routed_categories = list(routing.routing_categories) if routing else []
        max_categories = int(getattr(settings, "multi_category_max_categories", 2) or 2)
        max_categories = max(1, min(3, max_categories))

        if not routed_categories:
            router_fallback_used = True
        else:
            # Deduplicate categories while preserving order (first occurrence wins).
            seen: set[str] = set()
            deduped: list[RoutedCategory] = []
            for item in routed_categories:
                key = str(item.routing_category.value)
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(item)
                if len(deduped) >= max_categories:
                    break
            routed_categories = deduped

        if not routed_categories:
            # Deterministic fallback: single-category heuristic.
            fallback_category = classify_question(routing_question)
            routing = RoutingResult(
                routing_categories=[
                    RoutedCategory(
                        routing_category=fallback_category,
                        confidence=Confidence.medium,
                        budget=None,
                    )
                ]
            )
            routed_categories = list(routing.routing_categories)

        # Apply deterministic intent-based budgets (policy selected by config).
        max_total = int(getattr(settings, "multi_category_max_total_chunks", 5) or 5)
        max_total = max(1, max_total)
        policy = str(getattr(settings, "multi_category_budget_policy", "") or "")
        if policy.strip() != "deterministic":
            # Unknown policy version -> safest fallback.
            budgets = [max_total] + [1 for _ in routed_categories[1:]]
        else:
            budgets = _deterministic_budget_policy(
                question=routing_question,
                categories=routed_categories,
                max_total_chunks=max_total,
            )
        budgets = _clamp_budgets(
            categories=routed_categories,
            budgets=budgets,
            max_total_chunks=max_total,
        )

        routing = RoutingResult(
            routing_categories=[
                RoutedCategory(
                    routing_category=item.routing_category,
                    confidence=item.confidence,
                    budget=budgets[idx],
                )
                for idx, item in enumerate(routed_categories)
            ]
        )
        routing_category = routing.routing_categories[0].routing_category
    else:
        try:
            routing_category = route_category(standalone_question)
        except Exception:
            routing_category = classify_question(standalone_question)
    logger.info(
        "chat_stage",
        extra={
            "stage": "route_category_done",
            "duration_ms": round((time.perf_counter() - t_stage) * 1000, 2),
            "routing_category": str(routing_category),
        },
    )

    if use_multi_category and routing is not None:
        logger.info(
            "chat_routing",
            extra={
                "routing_categories": [
                    {
                        "routing_category": str(item.routing_category.value),
                        "confidence": str(item.confidence.value),
                        "budget": int(item.budget or 0),
                    }
                    for item in routing.routing_categories
                ],
                "max_categories": int(
                    getattr(settings, "multi_category_max_categories", 2) or 2
                ),
                "max_total_chunks": int(
                    getattr(settings, "multi_category_max_total_chunks", 5) or 5
                ),
                "router_fallback_used": bool(router_fallback_used),
            },
        )

    t_stage = time.perf_counter()
    logger.info(
        "chat_stage",
        extra={
            "stage": "retrieve_start",
            "topic_used_for_retrieval": use_topic_for_retrieval,
        },
    )
    if use_multi_category and routing is not None:
        chunks_by_category: dict[str, list] = {}
        # Get all section weights from settings
        all_section_weights = (
            getattr(settings, "multi_category_section_weights", {}) or {}
        )

        for item in routing.routing_categories:
            budget = int(item.budget or 1)
            category_label = str(item.routing_category.value)
            t_cat = time.perf_counter()

            # Get category-specific section weights (if any)
            category_section_weights = all_section_weights.get(category_label)

            selected = retrieve_for_category(
                standalone_question,
                routing_category=category_label,
                budget=budget,
                conversation_topic=conversation_topic,
                section_weights=category_section_weights,
            )
            chunks_by_category[category_label] = selected
            logger.info(
                "chat_retrieve_category",
                extra={
                    "routing_category": category_label,
                    "budget": budget,
                    "selected_count": len(selected),
                    "per_card_cap": int(
                        getattr(settings, "retrieval_per_card_cap", 2) or 2
                    ),
                    "duration_ms": round((time.perf_counter() - t_cat) * 1000, 2),
                    "section_weighting_enabled": bool(category_section_weights),
                },
            )

        merged, dedup_collisions = merge_dedup_preserve_provenance(chunks_by_category)

        # Apply pinning: ensure required cards are included for routed categories.
        # Pipeline: retrieve per category → merge → pin → re-dedup → cap → synthesis
        pinned_card_ids: list[str] = []
        routed_category_names = [
            str(i.routing_category.value) for i in routing.routing_categories
        ]
        max_total = int(getattr(settings, "multi_category_max_total_chunks", 5) or 5)
        max_total = max(1, max_total)

        # Get section weights for the first routed category (primary category for pinning).
        # This ensures pinned cards select the most relevant sections, not just low-distance
        # low-signal sections like "Category".
        primary_category_section_weights = (
            all_section_weights.get(routed_category_names[0])
            if routed_category_names
            else None
        )

        # Create a retrieval function for pinning that captures the current context.
        def _retrieve_for_pinning(card_id: str, limit: int):
            return retrieve_for_card(
                standalone_question,
                card_id=card_id,
                limit=limit,
                origin_routing_category=routed_category_names[0]
                if routed_category_names
                else "",
                conversation_topic=conversation_topic,
                section_weights=primary_category_section_weights,
            )

        merged, pinned_card_ids = apply_pinning(
            chunks=merged,
            pinning_rules=settings.multi_category_pinning_rules,
            routed_categories=routed_category_names,
            retrieve_for_card_fn=_retrieve_for_pinning,
            max_total_chunks=max_total,
        )

        # Re-dedup after pinning: pinned chunks may duplicate existing chunks.
        # Use a wrapper dict to reuse the merge_dedup_preserve_provenance function.
        if pinned_card_ids:
            merged_after_pin, _ = merge_dedup_preserve_provenance({"_pinned": merged})
            merged = merged_after_pin

        # Log pinning event if any cards were pinned.
        if pinned_card_ids:
            logger.info(
                "chat_pinning",
                extra={
                    "pinned_cards": pinned_card_ids,
                    "routed_categories": routed_category_names,
                },
            )

        chunks = cap_chunks_with_coverage(
            chunks=merged,
            routed_categories=routed_category_names,
            max_total_chunks=max_total,
        )

        logger.info(
            "chat_retrieve_merge",
            extra={
                "pre_dedup_count": sum(len(v) for v in chunks_by_category.values()),
                "post_dedup_count": len(merged),
                "dedup_collisions": dedup_collisions,
                "final_chunk_count": len(chunks),
                "pinned_card_ids": pinned_card_ids,
            },
        )
    else:
        chunks = retrieve(standalone_question, conversation_topic=conversation_topic)
    logger.info(
        "chat_stage",
        extra={
            "stage": "retrieve_done",
            "duration_ms": round((time.perf_counter() - t_stage) * 1000, 2),
            "retrieval_chunk_count": len(chunks),
        },
    )

    t_stage = time.perf_counter()
    logger.info(
        "chat_stage",
        extra={
            "stage": "synthesize_start",
            "retrieval_chunk_count": len(chunks),
        },
    )
    synthesis = synthesize_answer(
        standalone_question,
        chunks,
        routing_category,
        conversation_topic=conversation_topic,
        conversation_messages=[message.model_dump() for message in request.messages]
        if request.messages
        else None,
        routing=routing if use_multi_category else None,
    )

    # Quality gate + one retry (temperature=0) for multi-category answers.
    if use_multi_category and routing is not None:
        failure_reasons: list[str] = []
        refusal = "I do not have enough evidence in the provided materials."
        if synthesis.answer != refusal:
            if not synthesis.used_chunk_indices:
                failure_reasons.append("missing_used_chunk_indices")
            if len((synthesis.answer or "").split()) < 8:
                failure_reasons.append("answer_too_short")

            # Category coverage: for 2 categories, must use at least one chunk from each.
            if len(routing.routing_categories) == 2 and synthesis.used_chunk_indices:
                used = [
                    chunks[idx]
                    for idx in synthesis.used_chunk_indices
                    if isinstance(idx, int) and 0 <= idx < len(chunks)
                ]
                used_origins: set[str] = set()
                for ch in used:
                    if ch.origin_routing_category:
                        used_origins.add(ch.origin_routing_category)
                    for origin in ch.origin_routing_categories or []:
                        used_origins.add(origin)
                expected = {
                    str(i.routing_category.value) for i in routing.routing_categories
                }
                if expected and not expected.issubset(used_origins):
                    failure_reasons.append("missing_category_coverage")

        passed = not failure_reasons
        retry_attempted = False
        if not passed:
            retry_attempted = True
            synthesis_retry = synthesize_answer(
                standalone_question,
                chunks,
                routing_category,
                conversation_topic=conversation_topic,
                conversation_messages=[
                    message.model_dump() for message in request.messages
                ]
                if request.messages
                else None,
                routing=routing if use_multi_category else None,
                temperature_override=0,
                strict_facts_first=True,
            )
            synthesis = synthesis_retry

        logger.info(
            "chat_synthesis_quality_gate",
            extra={
                "passed": bool(passed),
                "failure_reasons": failure_reasons,
                "retry_attempted": bool(retry_attempted),
                "used_chunk_indices_count": len(synthesis.used_chunk_indices or []),
            },
        )

        # Hard post-condition: enforce multi-category coverage after retry.
        # If synthesis still doesn't use chunks from all routed categories,
        # force inclusion of at least one chunk from each missing category.
        if len(routing.routing_categories) > 1 and synthesis.used_chunk_indices:
            used = [
                chunks[idx]
                for idx in synthesis.used_chunk_indices
                if isinstance(idx, int) and 0 <= idx < len(chunks)
            ]
            used_origins: set[str] = set()
            for ch in used:
                if ch.origin_routing_category:
                    used_origins.add(ch.origin_routing_category)
                for origin in ch.origin_routing_categories or []:
                    used_origins.add(origin)
            expected = {
                str(i.routing_category.value) for i in routing.routing_categories
            }
            missing_categories = expected - used_origins

            if missing_categories:
                # Find one chunk from each missing category and force inclusion.
                forced_indices: list[int] = []
                for missing_cat in missing_categories:
                    for idx, ch in enumerate(chunks):
                        ch_origins = set(ch.origin_routing_categories or [])
                        if ch.origin_routing_category:
                            ch_origins.add(ch.origin_routing_category)
                        if (
                            missing_cat in ch_origins
                            and idx not in synthesis.used_chunk_indices
                        ):
                            forced_indices.append(idx)
                            break

                if forced_indices:
                    # Merge forced indices with existing ones.
                    new_indices = list(synthesis.used_chunk_indices) + forced_indices
                    synthesis = SynthesisResult(
                        answer=synthesis.answer,
                        why_this_matters=synthesis.why_this_matters,
                        confidence=synthesis.confidence,
                        confidence_reason=synthesis.confidence_reason,
                        used_chunk_indices=new_indices,
                    )
                    logger.info(
                        "chat_multi_category_forced_coverage",
                        extra={
                            "missing_categories": list(missing_categories),
                            "forced_indices": forced_indices,
                            "final_used_chunk_indices_count": len(new_indices),
                        },
                    )

        # Quality rules validation (log-only in v1, no retry trigger).
        # Validates answer against category-specific quality rules.
        quality_rules = getattr(settings, "multi_category_quality_rules", {}) or {}
        if quality_rules and synthesis.answer != refusal:
            category_validation_failures: list[dict] = []
            for item in routing.routing_categories:
                category_label = str(item.routing_category.value)
                result = validate_answer_quality(
                    answer=synthesis.answer or "",
                    routing_category=category_label,
                    quality_rules=quality_rules,
                )
                if not result.passed:
                    category_validation_failures.append(
                        {
                            "routing_category": category_label,
                            "failures": result.failure_reasons,
                        }
                    )

            if category_validation_failures:
                logger.info(
                    "chat_quality_rules_log_only",
                    extra={
                        "category_validation_failures": category_validation_failures,
                        "note": "v1 log-only mode, no retry triggered",
                    },
                )
    logger.info(
        "chat_stage",
        extra={
            "stage": "synthesize_done",
            "duration_ms": round((time.perf_counter() - t_stage) * 1000, 2),
            "answer_len": len(synthesis.answer or ""),
            "used_chunk_indices_count": len(synthesis.used_chunk_indices or []),
        },
    )

    refusal = "I do not have enough evidence in the provided materials."
    if synthesis.answer == refusal:
        logger.info(
            "chat_refusal_no_evidence",
            extra={
                "session_id": session_id,
                "conversation_id": conversation_id,
                "messages_count": messages_count,
                "incoming_last_topic": incoming_last_topic,
                "topic_used_for_retrieval": use_topic_for_retrieval,
                "retrieval_chunk_count": len(chunks),
            },
        )

    # Return evidence/sources only for chunks actually used in the answer.
    used_indices = [
        idx
        for idx in synthesis.used_chunk_indices
        if isinstance(idx, int) and 0 <= idx < len(chunks)
    ]
    used_chunks = [chunks[idx] for idx in used_indices]

    evidence = [
        EvidenceItem(snippet=chunk.content, card_id=chunk.card_id)
        for chunk in used_chunks
    ]
    sources = [
        SourceRef(card_id=chunk.card_id, section=chunk.section) for chunk in used_chunks
    ]

    resolved_topic = chunks[0].card_id if chunks else conversation_topic

    response = ChatResponse(
        routing_category=routing_category,
        answer=synthesis.answer,
        why_this_matters=clean_why(synthesis.why_this_matters, routing_category),
        evidence=evidence,
        sources=sources,
        debug_retrieval=[
            DebugRetrievalItem(
                card_id=chunk.card_id,
                section=chunk.section,
                distance=float(chunk.distance),
            )
            for chunk in chunks
            if debug_retrieval and chunk.distance is not None
        ]
        or None,
        confidence=synthesis.confidence,
        confidence_reason=synthesis.confidence_reason,
        routing=RoutingDebug(
            routing_categories=[
                RoutingCategoryAllocation(
                    routing_category=str(item.routing_category.value),
                    confidence=item.confidence,
                    budget=int(item.budget or 0),
                )
                for item in (routing.routing_categories if routing else [])
            ]
        )
        if (debug_retrieval and use_multi_category and routing is not None)
        else None,
        context=ConversationContext(
            conversation_id=conversation_id,
            last_topic=resolved_topic,
        ),
        formatted_answer="",
    )
    response.formatted_answer = format_answer(
        response.answer,
        response.why_this_matters,
        response.evidence,
        response.sources,
        response.confidence,
        response.confidence_reason,
    )

    response_at = datetime.now(UTC)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    # Best-effort interaction logging.
    #
    # NOTE: This performs blocking I/O (optional GeoIP HTTP call + DB write), so
    # it must not run on the main response path.
    try:
        tasks = background_tasks
        client_ip = extract_client_ip(http_request, settings)
        user_agent = http_request.headers.get("user-agent")

        conversation_messages_payload = (
            [message.model_dump() for message in request.messages]
            if request.messages
            else None
        )
        llm_context_messages = _build_llm_context_messages(
            conversation_messages_payload,
            max_messages=6,
            max_content_chars=2000,
        )

        # Build multi-category diagnostics for persistence.
        routing_dict: dict | None = None
        retrieval_by_category_dict: dict | None = None
        quality_gate_dict: dict | None = None

        if use_multi_category and routing is not None:
            routing_dict = {
                "routing_categories": [
                    {
                        "routing_category": str(item.routing_category.value),
                        "confidence": str(item.confidence.value),
                        "budget": int(item.budget or 0),
                    }
                    for item in routing.routing_categories
                ],
                "router_fallback_used": bool(router_fallback_used),
            }

        if use_multi_category and "chunks_by_category" in dir():
            retrieval_by_category_dict = {
                category: {
                    "selected_count": len(chunks),
                    "budget": int(
                        next(
                            (
                                item.budget
                                for item in (
                                    routing.routing_categories if routing else []
                                )
                                if str(item.routing_category.value) == category
                            ),
                            0,
                        )
                        or 0
                    ),
                }
                for category, chunks in chunks_by_category.items()
            }

        if use_multi_category and routing is not None:
            quality_gate_dict = {
                "passed": bool(passed) if "passed" in dir() else None,
                "failure_reasons": failure_reasons
                if "failure_reasons" in dir()
                else [],
                "retry_attempted": bool(retry_attempted)
                if "retry_attempted" in dir()
                else False,
            }

        tasks.add_task(
            _log_interaction_background,
            settings=settings,
            request_id=request_id,
            session_id=session_id,
            conversation_id=conversation_id,
            request_at=request_at,
            response_at=response_at,
            latency_ms=latency_ms,
            question=request.question,
            standalone_question=standalone_question,
            answer=response.answer,
            router_model=settings.router_model,
            synthesis_model=settings.synthesis_model,
            embeddings_provider=settings.embeddings_provider,
            embeddings_model=settings.embeddings_model,
            incoming_last_topic=incoming_last_topic,
            resolved_topic=resolved_topic,
            topic_used_for_retrieval=use_topic_for_retrieval,
            messages_count=messages_count,
            retrieval_chunk_count=len(chunks),
            llm_context_messages=llm_context_messages,
            client_ip=client_ip,
            user_agent=user_agent,
            routing=routing_dict,
            retrieval_by_category=retrieval_by_category_dict,
            quality_gate=quality_gate_dict,
        )
    except Exception:
        logger.exception("interaction_log_schedule_failed")

    return response
