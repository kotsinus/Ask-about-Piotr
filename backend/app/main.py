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
from app.llm import clean_why, rewrite_question, route_category, synthesize_answer
from app.logging_setup import configure_logging
from app.observability import (
    REQUEST_ID_HEADER,
    get_request_id,
    reset_request_id,
    set_request_id,
)
from app.privacy import anonymize_ip_prefix, extract_client_ip, hash_ip
from app.retrieval import retrieve
from app.schemas import (
    Category,
    ChatRequest,
    ChatResponse,
    Confidence,
    ConversationContext,
    DebugRetrievalItem,
    EvidenceItem,
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
    answer: str,
    router_model: str | None,
    synthesis_model: str | None,
    embeddings_provider: str | None,
    embeddings_model: str | None,
    client_ip: str | None,
    user_agent: str | None,
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
                answer=answer,
                router_model=router_model,
                synthesis_model=synthesis_model,
                embeddings_provider=embeddings_provider,
                embeddings_model=embeddings_model,
                ip_prefix=ip_prefix,
                ip_hash=ip_hash,
                user_agent=user_agent,
                country=country,
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


def classify_question(question: str) -> Category:
    """Classify the question into exactly one category.

    TODO: Replace with a deterministic classifier or a small ruleset.
    """

    text = question.lower()
    if any(keyword in text for keyword in ["team", "lead", "strategy", "roadmap"]):
        return Category.leadership_and_product_strategy
    if any(keyword in text for keyword in ["architecture", "design", "system"]):
        return Category.architecture_and_system_design
    if any(keyword in text for keyword in ["ml", "ai", "model", "embedding"]):
        return Category.ai_and_ml_practice
    if any(keyword in text for keyword in ["research", "paper", "publication"]):
        return Category.research_and_academic_credibility
    if any(keyword in text for keyword in ["role", "fit", "position"]):
        return Category.career_fit_and_role_alignment
    return Category.hands_on_engineering


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

    standalone_question = rewrite_question(
        request.question,
        [message.model_dump() for message in request.messages]
        if request.messages
        else None,
    )
    try:
        category = route_category(standalone_question)
    except Exception:
        category = classify_question(standalone_question)
    chunks = retrieve(standalone_question, conversation_topic=conversation_topic)

    synthesis = synthesize_answer(
        standalone_question,
        chunks,
        category,
        conversation_topic=conversation_topic,
        conversation_messages=[message.model_dump() for message in request.messages]
        if request.messages
        else None,
    )

    refusal = "I do not have enough evidence in the provided materials."
    if synthesis.answer == refusal:
        logger.warning(
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
        category=category,
        answer=synthesis.answer,
        why_this_matters=clean_why(synthesis.why_this_matters, category),
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
            answer=response.answer,
            router_model=settings.router_model,
            synthesis_model=settings.synthesis_model,
            embeddings_provider=settings.embeddings_provider,
            embeddings_model=settings.embeddings_model,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except Exception:
        logger.exception("interaction_log_schedule_failed")

    return response
