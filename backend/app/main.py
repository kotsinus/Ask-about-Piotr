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
from dataclasses import dataclass
from datetime import UTC, datetime

import hashlib

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import APIConnectionError, APIError, AuthenticationError, RateLimitError

from app.config import get_settings, get_web_settings
from app.geoip import lookup_country
from app.interaction_logging import InteractionLog, write_interaction_log
from app.llm import (
    RoutingCategory,
    RoutingResult,
    clean_why,
    deterministic_fallback_synthesis,
    is_laconic_answer,
    REFUSAL_MESSAGE,
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
from app.retrieval import (
    merge_dedup_and_cap,
    merge_retrieval_results_by_category,
    retrieve,
    retrieve_candidates_for_category,
    retrieve_for_category,
)
from app.schemas import (
    Category,
    ChatRequest,
    ChatResponse,
    Confidence,
    ConversationContext,
    DebugRetrievalItem,
    EvidenceItem,
    RoutingCategoryItem,
    RoutingResult as PublicRoutingResult,
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


_EDUCATION_TOKENS = (
    "university",
    "bsc",
    "msc",
    "phd",
    "degree",
    "master",
    "bachelor",
    "engineering",
    "faculty",
    "institute",
    "academy",
    "course",
    "studied",
    "graduat",
)


_ACTION_VERBS = (
    "built",
    "designed",
    "led",
    "shipped",
    "implemented",
    "deployed",
    "owned",
    "delivered",
)


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "its",
    "my",
    "of",
    "on",
    "or",
    "our",
    "she",
    "so",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "you",
    "your",
}


def _tokenize(text: str) -> set[str]:
    # Keep it simple and deterministic: alphanumerics and apostrophes.
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]{1,}", text or "")
    out: set[str] = set()
    for t in tokens:
        lowered = t.lower().strip("-'")
        if len(lowered) < 3:
            continue
        if lowered in _STOPWORDS:
            continue
        out.add(lowered)
    return out


def _intent_tokens(question: str) -> set[str]:
    # Generic intent approximation: salient tokens in the question.
    # (No domain logic; just a stable token set.)
    return _tokenize(question)


def _chunk_token_overlap(*, intent: set[str], chunk_text: str) -> int:
    if not intent:
        return 0
    chunk_tokens = _tokenize(chunk_text)
    return len(intent.intersection(chunk_tokens))


def _filter_chunks_by_intent(*, chunks: list, intent: set[str]) -> tuple[list, dict]:
    """Intent-aligned evidence filtering.

    Generic policy:
    - If we have any overlap>0 chunk, we demote/drop overlap==0 chunks.
    - Never drop to zero; keep at least 2 chunks when available.
    """

    if not chunks or not intent:
        return (list(chunks or []), {"intent_tokens_count": len(intent), "dropped": 0})

    scored: list[tuple[int, int, object]] = []
    for idx, c in enumerate(chunks):
        overlap = _chunk_token_overlap(intent=intent, chunk_text=str(getattr(c, "content", "") or ""))
        scored.append((idx, overlap, c))

    max_overlap = max((ov for _, ov, _ in scored), default=0)
    if max_overlap <= 0:
        # Can't reliably filter; keep original.
        return (list(chunks), {"intent_tokens_count": len(intent), "dropped": 0})

    # Keep all overlap>0.
    kept = [c for _, ov, c in scored if ov > 0]
    dropped = len(chunks) - len(kept)

    # If filtering is too aggressive, keep the best remaining chunks to reach 2.
    if len(kept) < 2 and len(chunks) >= 2:
        remaining = [c for _, ov, c in scored if ov <= 0]
        kept = [*kept, *remaining[: (2 - len(kept))]]
        dropped = len(chunks) - len(kept)

    return (kept, {"intent_tokens_count": len(intent), "dropped": int(max(0, dropped))})


def _count_tokens(text: str, tokens: tuple[str, ...]) -> int:
    lowered = (text or "").lower()
    return sum(1 for t in tokens if t in lowered)


def _count_named_examples(answer: str) -> int:
    """Heuristic for "named examples" per plan.

    Definition (stable): count bullet lines starting with "- <Label>:".
    Optionally require action verb presence to reduce false positives.
    """

    lines = [ln.rstrip() for ln in (answer or "").splitlines()]
    bullets = [ln.strip() for ln in lines if ln.strip().startswith("-")]
    count = 0
    for ln in bullets:
        # Expect "- Label: ..."
        m = re.match(r"^[-–—]\s*([A-Z][\w\-\s]{2,40}):\s+(.+)$", ln)
        if not m:
            continue
        tail = m.group(2).lower()
        if any(v in tail for v in _ACTION_VERBS):
            count += 1
    return count


def _derive_used_categories(
    *, used_indices: list[int], chunks: list
) -> list[str]:
    cats: list[str] = []
    for idx in used_indices or []:
        if not isinstance(idx, int) or idx < 0 or idx >= len(chunks):
            continue
        c = chunks[idx]
        cat = str(getattr(c, "best_origin_category", "") or "").strip()
        if not cat:
            # Fallback: if provenance missing, use chunk.category (knowledge category)
            cat = str(getattr(c, "category", "") or "").strip()
        if cat and cat not in cats:
            cats.append(cat)
    return cats


def _is_yes_no_question(question: str) -> bool:
    q = " ".join((question or "").strip().split()).lower()
    if not q:
        return False
    # Heuristic: starts with an auxiliary/modal. Ending with '?' is a weak signal,
    # so we only use it when the start token looks yes/no-like.
    starters = (
        "is ",
        "are ",
        "am ",
        "do ",
        "does ",
        "did ",
        "can ",
        "could ",
        "would ",
        "should ",
        "has ",
        "have ",
        "had ",
        "will ",
        "won't ",
        "isn't ",
        "aren't ",
        "doesn't ",
        "don't ",
        "didn't ",
        "can't ",
        "couldn't ",
        "wouldn't ",
        "shouldn't ",
        "hasn't ",
        "haven't ",
        "hadn't ",
    )
    if any(q.startswith(s) for s in starters):
        return True
    return False


def _answer_starts_with_yes_no(answer: str) -> bool:
    first = (answer or "").lstrip()
    if not first.startswith("-"):
        return False
    # First bullet begins with Yes/No.
    return bool(re.match(r"^[-–—]\s*(yes|no)\b", first, flags=re.IGNORECASE))


def _parse_answer_bullets(answer: str) -> list[str]:
    bullets: list[str] = []
    for ln in (answer or "").splitlines():
        stripped = ln.strip()
        if stripped.startswith("-"):
            bullet = re.sub(r"^[-–—]\s*", "", stripped).strip()
            if bullet:
                bullets.append(bullet)
    return bullets


def _why_off_topic(*, why: str, intent: set[str], bullets: list[str]) -> bool:
    tokens = _tokenize(why)
    if not tokens:
        return True
    anchor = set(intent)
    for b in bullets or []:
        anchor |= _tokenize(b)
    if not anchor:
        return False
    return len(tokens.intersection(anchor)) <= 0


def _bullets_have_evidence_support(*, bullets: list[str], evidence_chunks: list) -> bool:
    if not bullets:
        return False
    if not evidence_chunks:
        return False
    chunk_tokens = [
        _tokenize(str(getattr(c, "content", "") or "")) for c in (evidence_chunks or [])
    ]
    for b in bullets:
        bt = _tokenize(b)
        if not bt:
            return False
        # At least one evidence chunk must share a non-trivial token.
        if not any(len(bt.intersection(ct)) > 0 for ct in chunk_tokens):
            return False
    return True


def _quality_gate_validate(
    *,
    synthesis,
    chunks,
    routed_categories: list[Category],
    per_category_provided_counts: dict[str, int],
    is_yes_no_question: bool,
    intent_tokens: set[str],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    answer = str(getattr(synthesis, "answer", "") or "")
    refusal = REFUSAL_MESSAGE

    has_provenance = any(
        bool(getattr(c, "best_origin_category", None)) or bool(getattr(c, "origin_categories", None))
        for c in (chunks or [])
    )

    if answer != refusal:
        used = list(getattr(synthesis, "used_chunk_indices", []) or [])
        if not used:
            reasons.append("missing_used_chunk_indices")

        if is_laconic_answer(answer, refusal=refusal):
            reasons.append("laconic_answer")

        bullets = _parse_answer_bullets(answer)
        if not bullets:
            reasons.append("missing_fact_bullets")

        # Global rule: never allow Yes/No bullets.
        if _answer_starts_with_yes_no(answer):
            reasons.append("yes_no_bullet_disallowed")

        # Intent alignment: require that each bullet overlaps with intent tokens
        # when we have an intent signal.
        if intent_tokens:
            for b in bullets:
                if len(_tokenize(b).intersection(intent_tokens)) <= 0:
                    reasons.append("bullet_off_intent")
                    break

        # Bidirectional grounding check: every bullet must be supported by at
        # least one used evidence chunk.
        used_chunks = []
        for idx in used:
            if isinstance(idx, int) and 0 <= idx < len(chunks):
                used_chunks.append(chunks[idx])
        if used_chunks and bullets:
            if not _bullets_have_evidence_support(bullets=bullets, evidence_chunks=used_chunks):
                reasons.append("bullet_not_justified_by_evidence")

        # Why-this-matters alignment: must be a consequence of bullet facts and
        # relevant to the question intent; must not drift into unrelated domains.
        why = str(getattr(synthesis, "why_this_matters", "") or "")
        if _why_off_topic(why=why, intent=intent_tokens, bullets=bullets):
            reasons.append("why_off_topic")

        # Yes/No prefix correctness: if the question is NOT yes/no, the answer
        # must not start with a Yes/No bullet.
        if not bool(is_yes_no_question):
            if _answer_starts_with_yes_no(answer):
                reasons.append("unexpected_yes_no_prefix")

        # Category coverage: if exactly 2 routed cats and both had evidence provided,
        # require that used indices cover both.
        routed = [str(c.value) for c in (routed_categories or [])]
        if has_provenance and len(routed) == 2:
            provided_a = int(per_category_provided_counts.get(routed[0], 0) or 0)
            provided_b = int(per_category_provided_counts.get(routed[1], 0) or 0)
            if provided_a > 0 and provided_b > 0:
                used_cats = set(_derive_used_categories(used_indices=used, chunks=chunks))
                missing: list[str] = [c for c in routed if c not in used_cats]
                if missing:
                    reasons.append("missing_category_coverage")

        # Token checks.
        primary = routed_categories[0] if routed_categories else None
        if has_provenance and primary == Category.education_and_formal_background:
            if _count_tokens(answer, _EDUCATION_TOKENS) < 2:
                reasons.append("education_token_check_failed")

        # Experience/Production check: enforce when hands-on engineering is routed.
        if has_provenance and any(
            c == Category.hands_on_engineering for c in (routed_categories or [])
        ):
            if _count_named_examples(answer) < 2:
                reasons.append("experience_named_examples_failed")

    return (len(reasons) == 0, reasons)


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


def _stable_hash(value: str) -> int:
    digest = hashlib.sha256((value or "").encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def _is_multi_category_enabled(*, settings, request_id: str) -> bool:
    flag_on = bool(getattr(settings, "multi_category_retrieval_enabled", False))
    if not flag_on:
        return False
    rollout_percent = int(getattr(settings, "multi_category_rollout_percent", 0) or 0)
    rollout_percent = max(0, min(100, rollout_percent))
    if rollout_percent <= 0:
        return False
    rid = request_id or ""
    return (_stable_hash(rid) % 100) < rollout_percent


def _fallback_single_category_routing(
    *, question: str, max_total_chunks: int
) -> RoutingResult:
    category = classify_question(question)
    return RoutingResult(
        categories=[
            RoutingCategory(
                category=category,
                confidence="fallback",
                budget=max_total_chunks,
            )
        ]
    )


def _intent_rules_v1_budgets(
    *, question: str, categories: list[Category], max_total_chunks: int
) -> dict[Category, int]:
    # Deterministic server-side policy.
    # - For 1 category: allocate full budget to it.
    # - For 2 categories: if question signals education + hands-on engineering, allocate 2+3.
    # - Otherwise default to 3+2 without positional bias: higher budget goes to the category
    #   that matches engineering keywords if present.

    if not categories:
        return {}
    if len(categories) == 1:
        return {categories[0]: max_total_chunks}

    q = (question or "").lower()
    has_edu = any(k in q for k in ["education", "degree", "university", "background"])
    has_eng = any(
        k in q
        for k in [
            "build",
            "built",
            "engineer",
            "engineering",
            "system",
            "architecture",
            "production",
            "deploy",
            "debug",
            "implement",
            "implementation",
            "experience",
        ]
    )

    budgets: dict[Category, int] = {c: 1 for c in categories}
    remaining = max_total_chunks - len(categories)
    remaining = max(0, remaining)

    # Prefer explicit mapping for the 2-intent education + hands-on case.
    if (
        len(categories) == 2
        and has_edu
        and Category.education_and_formal_background in categories
        and Category.hands_on_engineering in categories
    ):
        budgets[Category.education_and_formal_background] = 2
        budgets[Category.hands_on_engineering] = max_total_chunks - 2
        return budgets

    # Default: 3+2 total (when max_total_chunks==5).
    if len(categories) == 2 and max_total_chunks >= 5:
        high = 3
        low = max_total_chunks - high
        pick_high = None
        if has_eng and Category.hands_on_engineering in categories:
            pick_high = Category.hands_on_engineering
        if pick_high is None:
            pick_high = categories[0]
        other = categories[1] if categories[0] == pick_high else categories[0]
        budgets[pick_high] = high
        budgets[other] = max(1, low)
        return budgets

    # Otherwise: spread remaining evenly.
    idx = 0
    cats = list(categories)
    while remaining > 0 and cats:
        budgets[cats[idx % len(cats)]] += 1
        remaining -= 1
        idx += 1
    return budgets


def _clamp_routing_result(
    *,
    question: str,
    result: RoutingResult,
    max_categories: int,
    max_total_chunks: int,
    allow_six_chunks: bool,
    budget_policy: str,
) -> RoutingResult:
    max_categories = max(1, int(max_categories))
    max_total_chunks = max(1, int(max_total_chunks))

    # Normalize/dedup categories preserving order.
    normalized: list[RoutingCategory] = []
    seen: set[Category] = set()
    for item in result.categories if result and result.categories else []:
        cat = item.category
        if cat in seen:
            continue
        seen.add(cat)
        normalized.append(item)
        if len(normalized) >= max_categories:
            break

    if not normalized:
        return _fallback_single_category_routing(
            question=question, max_total_chunks=max_total_chunks
        )

    # If router provided no usable budgets (<=0), use policy.
    router_budget_ok = all((c.budget or 0) > 0 for c in normalized)
    if router_budget_ok:
        budgets = {c.category: max(1, int(c.budget)) for c in normalized}
    else:
        cats = [c.category for c in normalized]
        if budget_policy != "intent_rules_v1":
            budget_policy = "intent_rules_v1"
        budgets = _intent_rules_v1_budgets(
            question=question,
            categories=cats,
            max_total_chunks=max_total_chunks,
        )
        for cat in cats:
            budgets.setdefault(cat, 1)

    # Enforce per-category minimums
    for cat in list(budgets.keys()):
        budgets[cat] = max(1, int(budgets[cat]))

    # Allow 6 only for 3-intent case (short-chunk case deferred).
    cap = max_total_chunks
    if allow_six_chunks and len(normalized) == 3:
        cap = max(cap, 6)

    # Clamp total budget.
    total = sum(budgets.get(c.category, 1) for c in normalized)
    if total > cap:
        # Reduce budgets deterministically from the largest down, keeping >=1.
        ordered = sorted(
            [c.category for c in normalized],
            key=lambda c: (budgets.get(c, 1), str(c)),
            reverse=True,
        )
        over = total - cap
        while over > 0:
            changed = False
            for cat in ordered:
                if over <= 0:
                    break
                if budgets.get(cat, 1) > 1:
                    budgets[cat] -= 1
                    over -= 1
                    changed = True
            if not changed:
                break

    # Final materialization in the same order.
    out_items: list[RoutingCategory] = []
    for item in normalized:
        out_items.append(
            RoutingCategory(
                category=item.category,
                confidence=item.confidence,
                budget=int(budgets.get(item.category, 1)),
            )
        )
    return RoutingResult(categories=out_items)


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
    multi_enabled = _is_multi_category_enabled(settings=settings, request_id=request_id)
    is_yes_no = _is_yes_no_question(standalone_question)
    router_fallback_used = False
    if not multi_enabled:
        logger.info(
            "chat_stage",
            extra={
                "stage": "route_category_start",
            },
        )
        try:
            category = route_category(standalone_question)
        except Exception:
            category = classify_question(standalone_question)
            router_fallback_used = True
        routing = RoutingResult(
            categories=[
                RoutingCategory(
                    category=category,
                    confidence="single",
                    budget=int(
                        getattr(settings, "multi_category_max_total_chunks", 5) or 5
                    ),
                )
            ]
        )
        logger.info(
            "chat_stage",
            extra={
                "stage": "route_category_done",
                "duration_ms": round((time.perf_counter() - t_stage) * 1000, 2),
                "category": str(category),
            },
        )
    else:
        logger.info(
            "chat_stage",
            extra={
                "stage": "route_categories_start",
            },
        )
        # Route on original_question (raw user input), NOT rewritten.
        try:
            raw_routing = route_categories(request.question)
        except Exception:
            raw_routing = RoutingResult(categories=[])
            router_fallback_used = True
        max_categories = int(getattr(settings, "multi_category_max_categories", 2) or 2)
        max_total = int(getattr(settings, "multi_category_max_total_chunks", 5) or 5)
        allow_six = bool(getattr(settings, "multi_category_allow_six_chunks", False))
        policy = str(
            getattr(settings, "multi_category_intent_budget_policy", "intent_rules_v1")
            or "intent_rules_v1"
        )
        routing = _clamp_routing_result(
            question=request.question,
            result=raw_routing,
            max_categories=max_categories,
            max_total_chunks=max_total,
            allow_six_chunks=allow_six,
            budget_policy=policy,
        )
        category = routing.categories[0].category
        logger.info(
            "chat_stage",
            extra={
                "stage": "route_categories_done",
                "duration_ms": round((time.perf_counter() - t_stage) * 1000, 2),
                "categories": [
                    {"category": str(c.category), "budget": int(c.budget)}
                    for c in routing.categories
                ],
            },
        )

    # Structured routing event (always before retrieval).
    logger.info(
        "chat_routing",
        extra={
            "categories": [
                {
                    "category": str(c.category),
                    "confidence": str(c.confidence),
                    "budget": int(c.budget),
                }
                for c in (routing.categories or [])
            ],
            "max_categories": int(getattr(settings, "multi_category_max_categories", 2) or 2),
            "max_total_chunks": int(getattr(settings, "multi_category_max_total_chunks", 5) or 5),
            "router_fallback_used": bool(router_fallback_used),
            "multi_enabled": bool(multi_enabled),
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

    retrieval_by_category_payload: dict | None = None
    per_category_selected: dict[str, list] | None = None
    if not multi_enabled:
        # Single-category retrieval (legacy behavior).
        chunks = retrieve(standalone_question, conversation_topic=conversation_topic)
    else:
        # Multi-category retrieval: per-category runs + merge/dedup/cap.
        per_category_selected = {}
        per_category_candidates: dict[str, list] = {}
        category_budgets: dict[str, int] = {}
        retrieval_by_category_payload = {
            "max_total_chunks": int(getattr(settings, "multi_category_max_total_chunks", 5) or 5),
            "categories": [],
        }
        per_card_cap = int(getattr(settings, "retrieval_per_card_cap", 2) or 2)
        section_weighting_enabled = True

        for item in routing.categories or []:
            cat = item.category
            budget = int(item.budget or 0)
            cat_key = str(cat.value)
            category_budgets[cat_key] = int(budget)
            oversample = int(getattr(settings, "multi_category_oversample_default", 5) or 5)
            try:
                mapping = getattr(settings, "multi_category_oversample_by_category", None) or {}
                if cat_key in mapping:
                    oversample = int(mapping.get(cat_key))
            except Exception:
                oversample = int(getattr(settings, "multi_category_oversample_default", 5) or 5)
            oversample = max(1, int(oversample))

            candidates = retrieve_candidates_for_category(
                standalone_question,
                cat,
                budget=int(budget),
                oversample_factor=oversample,
                conversation_topic=conversation_topic,
            )
            per_category_candidates[cat_key] = list(candidates)
            selected = list(candidates)[: max(0, int(budget))]
            # Note: retrieve_for_category already applies per-card cap and section weighting.
            # Invariant: per_category_selected keys are canonical category strings.
            per_category_selected[cat_key] = list(selected)

            logger.info(
                "chat_retrieve_category",
                extra={
                    "category": str(cat.value),
                    "budget": int(budget),
                    # Internal retrieve already returns the selected list.
                    "retrieved_count_raw": int(len(candidates)),
                    "selected_count": int(len(selected)),
                    "per_card_cap": int(per_card_cap),
                    "section_weighting_enabled": bool(section_weighting_enabled),
                },
            )
            retrieval_by_category_payload["categories"].append(
                {
                    "category": str(cat.value),
                    "budget": int(budget),
                    "selected_count": int(len(selected)),
                    "retrieved_count_raw": int(len(candidates)),
                }
            )

        max_total_chunks = int(getattr(settings, "multi_category_max_total_chunks", 5) or 5)
        merged_pre = [c for chunks_ in per_category_selected.values() for c in (chunks_ or [])]
        pre_dedup_count = int(len(merged_pre))

        merged_deduped = merge_retrieval_results_by_category(per_category_selected)
        post_dedup_count = int(len(merged_deduped))
        dedup_collisions = max(0, pre_dedup_count - post_dedup_count)

        # Merge/dedup/cap. This preserves provenance fields.
        routed_str = [str(c.category.value) for c in (routing.categories or [])]
        required_categories = None
        if len(routed_str) == 2:
            a, b = routed_str[0], routed_str[1]
            if len(per_category_selected.get(a, []) or []) > 0 and len(per_category_selected.get(b, []) or []) > 0:
                if max_total_chunks >= 2:
                    required_categories = [a, b]

        merged_final = merge_dedup_and_cap(
            question=standalone_question,
            per_category_selected=per_category_selected,
            routed_categories=[c.category for c in (routing.categories or [])],
            max_total_chunks=max_total_chunks,
            conversation_topic=conversation_topic,
            per_category_candidates=per_category_candidates,
            category_budgets=category_budgets,
        )
        chunks = list(merged_final)
        pinned_cards = sorted({str(c.card_id) for c in chunks if bool(getattr(c, "pinned", False))})

        # Observability: coverage satisfaction + meta-ish chunks.
        coverage_satisfied = True
        if required_categories:
            present = {str(getattr(c, "best_origin_category", "") or "") for c in chunks}
            coverage_satisfied = all(c in present for c in required_categories)
        from app.retrieval import _is_metaish_content as _metaish

        meta_chunk_count = sum(1 for c in chunks if _metaish(str(getattr(c, "content", "") or "")))

        logger.info(
            "chat_retrieve_merge",
            extra={
                "pre_dedup_count": int(pre_dedup_count),
                "post_dedup_count": int(post_dedup_count),
                "dedup_collisions": int(dedup_collisions),
                "pinned_cards": list(pinned_cards),
                "final_chunk_count": int(len(chunks)),
                "required_categories": list(required_categories or []),
                "coverage_satisfied": bool(coverage_satisfied),
                "meta_chunk_count": int(meta_chunk_count),
            },
        )
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
    # Quality-gated synthesis with one retry.
    routed_categories = [item.category for item in routing.categories] if routing else [category]
    routed_categories = [c for c in routed_categories if c]
    per_category_provided_counts: dict[str, int] = {}
    for c in chunks:
        key = str(getattr(c, "best_origin_category", "") or "").strip()
        if key:
            per_category_provided_counts[key] = per_category_provided_counts.get(key, 0) + 1

    intent = _intent_tokens(standalone_question)
    chunks, intent_filter_meta = _filter_chunks_by_intent(chunks=list(chunks), intent=intent)
    if multi_enabled:
        logger.info(
            "chat_evidence_intent_filter",
            extra={
                "intent_tokens_count": int(intent_filter_meta.get("intent_tokens_count", 0)),
                "dropped": int(intent_filter_meta.get("dropped", 0)),
                "final_chunk_count": int(len(chunks)),
            },
        )

    synthesis = synthesize_answer(
        standalone_question,
        chunks,
        category,
        conversation_topic=conversation_topic,
        conversation_messages=[message.model_dump() for message in request.messages]
        if request.messages
        else None,
        evidence_group_budgets=category_budgets if multi_enabled else None,
        is_yes_no_question=is_yes_no,
    )
    passed, failure_reasons = _quality_gate_validate(
        synthesis=synthesis,
        chunks=chunks,
        routed_categories=routed_categories,
        per_category_provided_counts=per_category_provided_counts,
        is_yes_no_question=is_yes_no,
        intent_tokens=intent,
    )

    retry_attempted = False
    if not passed and (synthesis.answer or "") != REFUSAL_MESSAGE and chunks:
        retry_attempted = True
        synthesis_retry = synthesize_answer(
            standalone_question,
            chunks,
            category,
            conversation_topic=conversation_topic,
            conversation_messages=[message.model_dump() for message in request.messages]
            if request.messages
            else None,
            evidence_group_budgets=category_budgets if multi_enabled else None,
            temperature=0,
            strict=True,
            is_yes_no_question=is_yes_no,
        )
        passed2, failure_reasons2 = _quality_gate_validate(
            synthesis=synthesis_retry,
            chunks=chunks,
            routed_categories=routed_categories,
            per_category_provided_counts=per_category_provided_counts,
            is_yes_no_question=is_yes_no,
            intent_tokens=intent,
        )
        if passed2:
            synthesis = synthesis_retry
            passed = True
            failure_reasons = []
        else:
            failure_reasons = failure_reasons2
            # Fall back to deterministic synthesis (never ungrounded).
            synthesis = deterministic_fallback_synthesis(chunks)

    used_count = len(getattr(synthesis, "used_chunk_indices", []) or [])
    used_categories = _derive_used_categories(used_indices=getattr(synthesis, "used_chunk_indices", []) or [], chunks=chunks)
    quality_gate_payload: dict | None = None
    if multi_enabled:
        quality_gate_payload = {
            "passed": bool(passed),
            "failure_reasons": list(failure_reasons),
            "retry_attempted": bool(retry_attempted),
            "used_chunk_indices_count": int(used_count),
            "used_categories": list(used_categories),
            "routed_categories": [str(c.value) for c in routed_categories],
            "provided_chunks_by_category": dict(per_category_provided_counts),
        }
    logger.info(
        "chat_synthesis_quality_gate",
        extra={
            "passed": bool(passed),
            "failure_reasons": list(failure_reasons),
            "retry_attempted": bool(retry_attempted),
            "used_chunk_indices_count": int(used_count),
            "used_categories": list(used_categories),
            "routed_categories": [str(c.value) for c in routed_categories],
            "provided_chunks_by_category": dict(per_category_provided_counts),
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

    if debug_retrieval:
        response.routing = PublicRoutingResult(
            categories=[
                RoutingCategoryItem(
                    category=item.category,
                    confidence=str(item.confidence),
                    budget=int(item.budget),
                )
                for item in routing.categories
            ]
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
            routing={
                "categories": [
                    {
                        "category": str(c.category.value),
                        "confidence": str(c.confidence),
                        "budget": int(c.budget),
                    }
                    for c in (routing.categories or [])
                ],
                "max_categories": int(getattr(settings, "multi_category_max_categories", 2) or 2),
                "max_total_chunks": int(getattr(settings, "multi_category_max_total_chunks", 5) or 5),
                "router_fallback_used": bool(router_fallback_used),
            }
            if multi_enabled
            else None,
            retrieval_by_category=retrieval_by_category_payload if multi_enabled else None,
            quality_gate=quality_gate_payload if multi_enabled else None,
        )
    except Exception:
        logger.exception("interaction_log_schedule_failed")

    return response
