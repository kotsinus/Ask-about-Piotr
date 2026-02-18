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
# Produces grounded answer text from retrieved evidence.
#
# Notes:
# This is a deterministic placeholder until an LLM is integrated.

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from app.config import get_settings
from app.openai_client import chat_completions_create, chat_completions_create_cached
from app.retrieval import RetrievedChunk
from app.routing_category import RoutingCategory
from app.schemas import Confidence

logger = logging.getLogger(__name__)


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _extract_last_user_questions(
    messages: list[dict] | None,
    *,
    max_questions: int = 4,
) -> list[str]:
    if not messages:
        return []

    user_contents: list[str] = []
    for m in messages:
        if str(m.get("role", "")).strip().lower() != "user":
            continue
        content = _normalize_ws(str(m.get("content", "")))
        if content:
            user_contents.append(content)

    if max_questions <= 0:
        return []
    return user_contents[-max_questions:]


def _content_tokens(text: str) -> set[str]:
    """Extract language-agnostic "content" tokens for overlap checks.

    We intentionally avoid language-specific stopword lists.

    Heuristic:
    - Tokenize on Unicode "word" characters (letters/digits across languages).
    - Keep tokens that are likely to carry meaning:
      - length >= 3 OR contains any digit
    """

    if not text:
        return set()

    raw = re.findall(r"\w+", text, flags=re.UNICODE)
    out: set[str] = set()
    for tok in raw:
        t = tok.strip().lower()
        if not t:
            continue
        if len(t) >= 3 or any(ch.isdigit() for ch in t):
            out.add(t)
    return out


def _is_token_derived(new_tok: str, allowed_tok: str) -> bool:
    """Heuristic: allow benign disambiguation tokens derived from history.

    The rewrite guardrail blocks hallucinated *facts* by rejecting unrelated
    content tokens. However, follow-up rewrites sometimes need to add small
    clarifiers that are lexical/morphological variants of something the user
    already said (e.g. "programming" derived from "program").

    Rules (case-insensitive):
    - shared prefix length >= 4, OR
    - one token is a substring of the other AND the shorter length >= 4.
    """

    a = (new_tok or "").strip().lower()
    b = (allowed_tok or "").strip().lower()
    if not a or not b:
        return False

    # Common prefix length.
    common = 0
    for ch1, ch2 in zip(a, b):
        if ch1 != ch2:
            break
        common += 1
    if common >= 4:
        return True

    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) >= 4 and shorter in longer:
        return True

    return False


def _looks_like_short_followup(question: str) -> bool:
    q = _normalize_ws(question)
    if not q:
        return False

    # Language-agnostic follow-up heuristic:
    # - short inputs are frequently context-dependent when there is prior history
    # - we intentionally do NOT rely on any language-specific pronoun lists
    token_count = len(re.findall(r"\w+", q, flags=re.UNICODE))
    char_len = len(q)

    if char_len <= 32:
        return True
    if token_count <= 6 and char_len <= 60:
        return True
    return False


def _is_single_sentence(text: str) -> bool:
    t = _normalize_ws(text)
    if not t:
        return False
    if "\n" in t:
        return False
    # Split on sentence terminators followed by whitespace.
    parts = [p for p in re.split(r"(?<=[.!?])\s+", t) if p]
    return len(parts) == 1


def _is_ambiguous_standalone(
    standalone_question: str,
    *,
    last_user_questions: list[str],
) -> bool:
    q = _normalize_ws(standalone_question)
    if not q:
        return True

    # Only punctuation / whitespace => not a meaningful standalone question.
    if re.fullmatch(r"[^\w]+", q, flags=re.UNICODE):
        return True

    token_count = len(re.findall(r"\w+", q, flags=re.UNICODE))
    char_len = len(q)
    # Extremely short questions are frequently follow-ups (context-dependent).
    # Keep this language-agnostic: we use only length/token heuristics.
    if token_count <= 3 and char_len < 20:
        return True

    candidate_tokens = _content_tokens(q)
    if not candidate_tokens:
        return True

    # If it's short AND shares no content tokens with recent user questions,
    # it's likely still context-dependent.
    history_tokens: set[str] = set()
    for h in last_user_questions:
        history_tokens |= _content_tokens(h)

    # If there's *no* overlap with recent user questions, treat it as ambiguous
    # only when the candidate is extremely short (otherwise we risk false
    # positives for standalone short questions when the client sends a trimmed
    # message window).
    if history_tokens and len(candidate_tokens) <= 2 and not (candidate_tokens & history_tokens):
        return True

    return False


def rewrite_question(question: str, messages: list[dict] | None = None) -> str:
    """Rewrite a short follow-up into a standalone question, then use it for routing.

    Rewrite inputs:
    - last 2-4 user questions (extracted from `messages`)
    - the original question

    Contract (LLM JSON output):
      {"standalone_question": "..."}

    Validation + retry:
    - If output remains ambiguous (context-dependent), retry.
    - If output introduces new content tokens not present in (original ∪ history), retry.

    If no OpenAI API key is configured, returns the original question.
    """

    original_question = _normalize_ws(question)
    if not original_question:
        return question

    last_user_questions = _extract_last_user_questions(messages, max_questions=4)
    last_user_questions = last_user_questions[-4:]

    # Only rewrite when it looks like a short follow-up and we have user history.
    rewrite_was_followup = bool(last_user_questions) and _looks_like_short_followup(
        original_question
    )
    if not rewrite_was_followup:
        return question

    settings = get_settings()
    if not settings.openai_api_key:
        return question

    # Keep prompt stable and cheap: limit to last 2-4 user questions.
    # Prefer at least 2 when available.
    user_qs = last_user_questions[-4:]
    if len(user_qs) > 2:
        user_qs = user_qs[-4:]
    # Ensure we don't pass more than 4.
    user_qs = user_qs[-4:]

    max_chars = 180
    max_attempts = 3
    validation_failures: list[str] = []

    def _build_system_prompt(*, strict: bool, attempt: int) -> str:
        base = (
            "Rewrite the user's latest message into a SINGLE standalone question.\n"
            "Use ONLY the provided previous user questions to resolve references.\n"
            "Do NOT add new facts or assumptions.\n"
            "Do NOT introduce new content words that do not appear in the original question or the previous user questions.\n"
            "If the original question is already standalone, you may return it unchanged.\n"
            "Output must be exactly one sentence.\n"
            f"Output must be <= {max_chars} characters.\n"
            "Output must not contain unresolved context-dependent references.\n"
            "Do NOT include preambles, explanations, or any keys other than standalone_question.\n"
            'Return strict JSON exactly: {"standalone_question": "..."}.\n'
        )
        if strict:
            base += (
                "\nSTRICT RETRY RULES:\n"
                "- You MUST replace context-dependent references with explicit nouns from the previous user questions.\n"
                "- Only make the minimal changes needed to make it standalone.\n"
            )
        # Cache-busting / traceability.
        base += f"\nAttempt: {attempt}/{max_attempts}"
        return base

    def _build_user_prompt() -> str:
        lines = [
            "Previous user questions (most recent last):",
        ]
        for idx, q in enumerate(user_qs, start=1):
            lines.append(f"{idx}. {q}")
        lines += ["", "Original question:", original_question]
        return "\n".join(lines)

    last_output: str | None = None
    for attempt in range(1, max_attempts + 1):
        strict = attempt >= 2
        system_prompt = _build_system_prompt(strict=strict, attempt=attempt)
        user_prompt = _build_user_prompt()

        response = chat_completions_create_cached(
            cache_namespace="rewrite_question_v2",
            model=settings.router_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = response.choices[0].message.content or "{}"
        try:
            payload = json.loads(content)
        except Exception:
            validation_failures.append("non_json")
            last_output = None
            continue

        candidate = _normalize_ws(str(payload.get("standalone_question", "")))
        last_output = candidate
        if not candidate:
            validation_failures.append("empty")
            continue

        # Ensure it's a question (lightweight enforcement).
        if "?" not in candidate:
            if len(candidate) + 1 <= max_chars:
                candidate = candidate.rstrip(".") + "?"
            else:
                validation_failures.append("missing_question_mark")
                continue

        if len(candidate) > max_chars:
            validation_failures.append("too_long")
            continue

        if not _is_single_sentence(candidate):
            validation_failures.append("not_single_sentence")
            continue

        # Validation: prevent the rewrite from introducing new content tokens
        # that weren't present in the original question or the provided history.
        # This is intentionally language-agnostic and uses the same token
        # extraction heuristic as ambiguity checks.
        allowed_tokens: set[str] = set()
        allowed_tokens |= _content_tokens(original_question)
        for h in user_qs:
            allowed_tokens |= _content_tokens(h)

        candidate_tokens = _content_tokens(candidate)
        introduced = candidate_tokens - allowed_tokens
        if introduced:
            # Relaxation: allow tokens that are lexical/morphological variants
            # of allowed tokens (derived from original question or history).
            unrelated_introduced = {
                tok
                for tok in introduced
                if not any(_is_token_derived(tok, allowed) for allowed in allowed_tokens)
            }
            if unrelated_introduced:
                validation_failures.append("introduced_new_tokens")
                continue

        # Retry if still ambiguous.
        if _is_ambiguous_standalone(candidate, last_user_questions=user_qs):
            validation_failures.append("ambiguous")
            continue

        return candidate

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "rewrite_question_failed_validation",
            extra={
                "validation_failures": validation_failures,
                "original_question": original_question,
                "last_output": last_output,
            },
        )

    return question


@dataclass(frozen=True)
class SynthesisResult:
    answer: str
    why_this_matters: str
    confidence: Confidence
    confidence_reason: str | None
    used_chunk_indices: list[int]


@dataclass(frozen=True)
class RoutedCategory:
    routing_category: RoutingCategory
    confidence: Confidence
    budget: int | None = None


@dataclass(frozen=True)
class RoutingResult:
    routing_categories: list[RoutedCategory]


def route_categories(question: str) -> RoutingResult:
    """Route a question into 1-3 routing categories.

    NOTE: This function performs only minimal parsing/validation. Deterministic
    clamping + budget policy is enforced server-side in `chat()`.

    Contract (LLM JSON output):
    {
      "routing_categories": [
        {"routing_category": "...", "confidence": "High|Medium|Low", "budget": 2},
        ...
      ]
    }

    Backward compatibility:
    - Accepts legacy key names `categories` / `category`.
    """

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for routing.")

    allowed_routing_categories = [str(c.value) for c in RoutingCategory]
    allowed_norm = {c.strip().lower() for c in allowed_routing_categories}

    system_prompt = (
        "Classify the question into 1 to 3 categories from this list:\n"
        + "\n".join(f"- {c}" for c in allowed_routing_categories)
        + "\n\n"
        "Rules:\n"
        "- Return 1 category for single-intent questions, 2 for two-part questions, and 3 only if clearly three-part.\n"
        "- Confidence must be one of: High, Medium, Low.\n"
        "- Provide an integer budget per category (>=1). If unsure, choose budgets that sum to 5 for two categories (2+3).\n\n"
        'Return JSON exactly like: {"routing_categories": [{"routing_category": "...", "confidence": "High", "budget": 2}]}.'
        "\n"
        "Do not add any other keys."
    )

    response = chat_completions_create_cached(
        cache_namespace="route_categories",
        model=settings.router_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    content = response.choices[0].message.content or "{}"
    payload = json.loads(content)

    # Backward-compatible: accept legacy key `categories`.
    raw_categories = payload.get("routing_categories")
    if raw_categories is None:
        raw_categories = payload.get("categories")
    if not isinstance(raw_categories, list) or not raw_categories:
        raise ValueError("Router returned no categories")

    parsed: list[RoutedCategory] = []
    for item in raw_categories:
        if not isinstance(item, dict):
            continue

        raw_routing_category = str(
            item.get("routing_category") or item.get("category") or ""
        ).strip()
        if raw_routing_category.strip().lower() not in allowed_norm:
            raise ValueError(
                f"Router returned unknown routing_category: {raw_routing_category}"
            )
        routing_category = _parse_routing_category(raw_routing_category)

        confidence = _parse_confidence(str(item.get("confidence", "")))
        budget_value = item.get("budget")
        budget: int | None = None
        if budget_value is not None:
            try:
                budget = int(budget_value)
            except Exception:
                budget = None

        parsed.append(
            RoutedCategory(
                routing_category=routing_category, confidence=confidence, budget=budget
            )
        )

    if not parsed:
        raise ValueError("Router returned no valid routing_categories")

    return RoutingResult(routing_categories=parsed)


def route_category(question: str) -> RoutingCategory:
    """Route a question into exactly one routing category using a low-cost model."""

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for routing.")

    system_prompt = (
        "Classify the question into exactly one category from this list:\n"
        "- Hands-on engineering\n"
        "- Architecture and system design\n"
        "- AI and ML practice\n"
        "- Leadership and product strategy\n"
        "- Research and academic credibility\n"
        "- Education and formal background\n"
        "- Personal interests and working style\n"
        "- Career fit and role alignment\n\n"
        'Return JSON exactly like: {"routing_category": "<one of the list items>"}.'
        "\n"
        "Do not add any other keys."
    )

    response = chat_completions_create_cached(
        cache_namespace="route_category",
        model=settings.router_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    content = response.choices[0].message.content or "{}"
    payload = json.loads(content)
    # Backward-compatible: accept legacy key `category`.
    return _parse_routing_category(
        payload.get("routing_category") or payload.get("category") or ""
    )


def synthesize_answer(
    question: str,
    chunks: list[RetrievedChunk],
    routing_category: str | RoutingCategory | None = None,
    conversation_topic: str | None = None,
    conversation_messages: list[dict] | None = None,
    routing: RoutingResult | None = None,
    *,
    temperature_override: float | None = None,
    strict_facts_first: bool = False,
    force_use_chunk_indices: list[int] | None = None,
) -> SynthesisResult:
    """Generate a strict, grounded answer from retrieved chunks."""

    if not chunks:
        return SynthesisResult(
            answer="I do not have enough evidence in the provided materials.",
            why_this_matters=(
                "The system must cite retrieved knowledge cards, and none were found."
            ),
            confidence=Confidence.low,
            confidence_reason="No relevant knowledge cards were retrieved for this question.",
            used_chunk_indices=[],
        )

    settings = get_settings()
    if not settings.openai_api_key:
        return _fallback_synthesis(chunks)

    def _chunk_origin(chunk: RetrievedChunk) -> str:
        if getattr(chunk, "origin_routing_category", None):
            return str(chunk.origin_routing_category)
        origins = getattr(chunk, "origin_routing_categories", None) or []
        if origins:
            return str(origins[0])
        return ""

    def _format_chunk_line(idx: int, chunk: RetrievedChunk) -> str:
        origin_routing_categories = (
            getattr(chunk, "origin_routing_categories", None) or []
        )
        origin_hint = ""
        if origin_routing_categories:
            origin_hint = (
                f" | origin_routing_categories={','.join(origin_routing_categories)}"
            )
        return f"[{idx}] [{chunk.card_id}.{chunk.section}]{origin_hint} {chunk.content}"

    evidence_block: str
    if (
        routing is not None
        and len(getattr(routing, "routing_categories", []) or []) > 1
    ):
        # Group evidence by routed category while preserving global indices.
        by_category: dict[str, list[tuple[int, RetrievedChunk]]] = {}
        for idx, chunk in enumerate(chunks):
            group = _chunk_origin(chunk) or "unknown"
            by_category.setdefault(group, []).append((idx, chunk))

        routing_order = [
            str(item.routing_category.value) for item in routing.routing_categories
        ]
        ordered_categories = [c for c in routing_order if c in by_category]
        # Append any categories that appear only via dedup/provenance.
        for cat in sorted(by_category.keys()):
            if cat not in ordered_categories:
                ordered_categories.append(cat)

        lines: list[str] = ["Evidence groups (global indices):", ""]
        budget_by_category = {
            str(item.routing_category.value): int(item.budget or 0)
            for item in routing.routing_categories
        }
        for cat in ordered_categories:
            items = by_category.get(cat, [])
            budget = budget_by_category.get(cat)
            header = f"Category: {cat}"
            if budget is not None:
                header += f" | budget {budget} | provided {len(items)}"
            lines.append(header)
            for idx, chunk in items:
                lines.append(_format_chunk_line(idx, chunk))
            lines.append("")
        evidence_block = "\n".join(lines).strip()
    else:
        evidence_lines = [
            _format_chunk_line(idx, chunk) for idx, chunk in enumerate(chunks)
        ]
        evidence_block = "Evidence:\n" + "\n".join(evidence_lines)

    STYLE_HINTS = {
        "Hands-on engineering": (
            "Be practical and concrete. Mention steps or implementation details only when supported by evidence."
        ),
        "Architecture and system design": (
            "Focus on system boundaries, trade-offs, and key design decisions. Keep it concrete."
        ),
        "AI and ML practice": (
            "Focus on models, evaluation, data, and failure modes. Avoid hype and generic statements."
        ),
        "Leadership and product strategy": (
            "Focus on decisions, alignment, outcomes, and team/process aspects. Avoid buzzwords."
        ),
        "Research and academic credibility": (
            "Be precise. Reference publications/patents by name only if they appear in evidence."
        ),
        "Education and formal background": (
            "Be factual and concise. Degrees, institutions, dates only if in evidence. "
            "For why_this_matters, mention foundations or perspective only. "
            "Do not reference later job experience, leadership, or role fit unless explicitly in evidence."
        ),
        "Career fit and role alignment": (
            "Be human and direct. Tie evidence to fit. Avoid generic claims like 'I am well-suited' or 'crucial'."
        ),
        "Personal interests and working style": (
            "Keep it light and short, but grounded. Avoid oversharing or anything too personal."
        ),
    }

    WHY_HINTS = {
        "Hands-on engineering": (
            "Explain practical relevance in terms of reliability, maintainability, performance, cost, or delivery risk."
        ),
        "Architecture and system design": (
            "Explain why the architectural trade-off matters for scalability, operability, security, or long-term complexity."
        ),
        "AI and ML practice": (
            "Explain why it matters for model quality, evaluation rigor, failure modes, or production reliability."
        ),
        "Leadership and product strategy": (
            "Explain why it matters for alignment, execution, stakeholder outcomes, or team effectiveness."
        ),
        "Research and academic credibility": (
            "Explain why it matters for rigor, novelty, or credibility. Do not claim impact not shown in evidence."
        ),
        "Education and formal background": (
            "Explain why it matters as foundational training or perspective. "
            "Do not reference later job experience unless explicitly mentioned in evidence."
        ),
        "Career fit and role alignment": (
            "Explain why it matters for role fit using concrete evidence. Avoid generic motivation statements."
        ),
        "Personal interests and working style": (
            "Explain relevance briefly in terms of collaboration, communication, or long-term consistency. Keep it light."
        ),
    }

    multi_category = bool(
        routing is not None
        and len(getattr(routing, "routing_categories", []) or []) > 1
    )

    category_key = _normalize_routing_category(routing_category)
    style_hint = STYLE_HINTS.get(category_key, "")
    why_hint = WHY_HINTS.get(category_key, "")

    # Keep hints in the user prompt for SINGLE-category only.
    # For multi-category, per-category hints are appended to the system prompt
    # to avoid a primary-category bias.
    hint_block = ""
    if not multi_category:
        if style_hint:
            hint_block += f"Answer style hint: {style_hint}\n"
        if why_hint:
            hint_block += f"Why-this-matters hint: {why_hint}\n"
        if hint_block:
            hint_block += "\n"

    # Include current date so LLM knows past dates are in the past
    now = datetime.now(UTC)
    current_date_str = now.strftime("%Y-%m-%d")

    system_prompt = (
        f"Current date: {current_date_str}\n\n"
        "You are Piotr Synak. Answer in first person (I, my) as if speaking to a technical peer. "
        "Do not mention that you are an AI, a model, or that you were prompted.\n\n"
        "Grounding rules:\n"
        "- Use ONLY the provided evidence.\n"
        "- Conversation context may help interpret the question but is NOT evidence.\n"
        "- If evidence is insufficient, return the exact refusal message and nothing else.\n"
        "- If you use evidence, you MUST list which evidence items were used via their indices.\n"
        "- If evidence states a degree or certification is completed, you must state it as completed. You must not change its completion status or tense in any way.\n\n"
        "Style rules (important):\n"
        "- Write like a person speaking, not like a CV or an essay.\n"
        "- The 'answer' field MUST be facts-first.\n"
        "- Use 2 to 6 sentences in the 'answer' field.\n"
        "- Prefer short, direct sentences. Avoid fluff and generic phrases.\n"
        "- Avoid meta-commentary such as: 'This highlights', 'This demonstrates', 'Understanding X is crucial', 'It is important to note'.\n"
        "- Do not restate the question. Do not introduce yourself.\n\n"
        "You may adapt depth to the style hint, but never change grounding rules.\n\n"
        "Yes/No questions:\n"
        "- Start with 'Yes' or 'No' in the answer field.\n"
        "- Then justify using evidence.\n\n"
        "Length constraints:\n"
        "- The 'answer' field should be between 25 and 130 words unless the refusal message is used.\n\n"
        "Return JSON with the following fields only:\n"
        '{"answer", "why_this_matters", "confidence", "confidence_reason", "used_chunk_indices"}.\n'
        "Use confidence values: High, Medium, or Low.\n"
        "- 'why_this_matters' must be 1 to 2 sentences and explain practical relevance (how this affects my work, decisions, or fit), not a generic motivation.\n"
        "- Avoid generic phrases in 'why_this_matters' such as: 'crucial', 'demonstrates', 'aligns with', 'highlights', 'enhances my ability', 'it is important to note'.\n"
        "- Keep 'why_this_matters' grounded in the same evidence. If evidence does not support a specific implication, keep it short and modest.\n"
        "The refusal message is exactly:\n"
        '"I do not have enough evidence in the provided materials."'
    )

    if strict_facts_first:
        system_prompt += (
            "\n\nSTRICT MODE (retry):\n"
            "- Follow the Facts/Synthesis structure exactly.\n"
            "- Facts must be concrete and attributable to evidence items.\n"
            "- Do not output generic filler.\n"
        )

    # Multi-category coverage requirement with structured synthesis.
    if multi_category:
        routing_category_names = [
            str(item.routing_category.value) for item in routing.routing_categories
        ]
        system_prompt += (
            "\n\nMulti-category requirement:\n"
            f"- This question was routed to {len(routing_category_names)} routing categories: {', '.join(routing_category_names)}.\n"
            "- You MUST use at least one chunk from EACH routed category.\n"
            "- If possible, structure your answer into short paragraphs/sections, one per routed category in order.\n"
            "- Each paragraph must be grounded in evidence from its corresponding category.\n"
        )

        if force_use_chunk_indices:
            forced = [
                int(i)
                for i in force_use_chunk_indices
                if isinstance(i, int) and 0 <= int(i) < len(chunks)
            ]
            if forced:
                forced_str = ", ".join(str(i) for i in forced)
                system_prompt += (
                    "\nHard evidence-use requirement (retry):\n"
                    f"- You MUST include at least one concrete fact from EACH of these evidence items: {forced_str}.\n"
                    "- Ensure the answer text explicitly reflects those facts (do not just cite them).\n"
                )

        # Add per-category mini-hints derived from STYLE_HINTS/WHY_HINTS.
        per_category_hints: list[str] = []
        for item in routing.routing_categories:
            cat_name = str(item.routing_category.value)
            cat_style = STYLE_HINTS.get(cat_name, "")
            cat_why = WHY_HINTS.get(cat_name, "")
            if cat_style or cat_why:
                hint_parts = [f"For '{cat_name}':"]
                if cat_style:
                    # Truncate style hint to first sentence for brevity
                    first_sentence = cat_style.split(". ")[0] + "."
                    hint_parts.append(f"  Style: {first_sentence}")
                if cat_why:
                    # Truncate why hint to first sentence for brevity
                    first_sentence = cat_why.split(". ")[0] + "."
                    hint_parts.append(f"  Focus: {first_sentence}")
                per_category_hints.append("\n".join(hint_parts))

        if per_category_hints:
            system_prompt += "\n\nPer-category hints:\n" + "\n".join(per_category_hints)
    else:
        # Single-category: bind category hints at system level to reduce model guessing/drift.
        if style_hint:
            system_prompt += f"\n\nStyle hint:\n{style_hint}\n"
        if why_hint:
            system_prompt += f"\n\nWhy-this-matters hint:\n{why_hint}\n"
    context_block = ""
    if conversation_messages:
        trimmed = conversation_messages[-6:]
        context_lines = [
            f"{m.get('role', '')}: {m.get('content', '')}" for m in trimmed
        ]
        context_block = (
            "Conversation context (for interpretation only; not evidence):\n"
            + "\n".join(context_lines)
            + "\n\n"
        )
    topic_line = (
        f"Conversation topic: {conversation_topic}\n\n" if conversation_topic else ""
    )

    user_prompt = (
        "Question:\n"
        f"{question}\n\n" + hint_block + context_block + topic_line + evidence_block
    )
    # NOTE: synthesize_answer is intentionally *not* routed through the local
    # response cache. We run it with a non-zero temperature by default, so
    # caching would be misleading at best (and incorrect at worst).
    response = chat_completions_create(
        model=settings.synthesis_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=settings.synthesis_temperature
        if temperature_override is None
        else float(temperature_override),
    )

    content = response.choices[0].message.content or "{}"
    payload = json.loads(content)

    answer = str(payload.get("answer", "")).strip()
    if not answer:
        return _fallback_synthesis(chunks)

    refusal = "I do not have enough evidence in the provided materials."

    if answer != refusal:
        normalized = answer.strip().lower()
        word_count = len(answer.split())

        # Guardrail: prevent laconic answers that violate the contract
        # (e.g. "Yes", "No", "I don't know", etc.)
        if normalized in {"yes", "no"} or word_count < 4:
            logger.warning(
                "synthesis_answer_too_short_fallback",
                extra={
                    "answer": answer,
                    "word_count": word_count,
                },
            )
            return _fallback_synthesis(chunks)

    used_chunk_indices: list[int] = []
    if answer != refusal:
        raw_indices = payload.get("used_chunk_indices", [])
        if not isinstance(raw_indices, list):
            raw_indices = []
        for value in raw_indices:
            try:
                idx = int(value)
            except Exception:
                continue
            if 0 <= idx < len(chunks) and idx not in used_chunk_indices:
                used_chunk_indices.append(idx)
        if not used_chunk_indices:
            # Safety: if the model didn't provide indices, fall back to "all" to
            # avoid returning an answer with no traceable evidence.
            used_chunk_indices = list(range(len(chunks)))

    confidence = _parse_confidence(str(payload.get("confidence", "")))
    confidence_reason = payload.get("confidence_reason")

    return SynthesisResult(
        answer=answer,
        why_this_matters=str(payload.get("why_this_matters", "")).strip()
        or "This answer is grounded in retrieved knowledge cards.",
        confidence=confidence,
        confidence_reason=str(confidence_reason).strip()
        if confidence == Confidence.low and confidence_reason
        else None,
        used_chunk_indices=used_chunk_indices,
    )


def _split_sentences(text: str) -> list[str]:
    return [segment for segment in re.split(r"(?<=[.!?])\s+", text) if segment]


def _fallback_synthesis(chunks: list[RetrievedChunk]) -> SynthesisResult:
    # Deterministic synthesis used when no LLM is configured.
    #
    # Goal: be reasonably verbose while staying strictly grounded.
    sentences: list[str] = []
    used_chunk_indices: list[int] = []
    max_sentences = 10
    max_sentences_per_chunk = 2

    for idx, chunk in enumerate(chunks):
        chunk_sentences = []
        for sentence in _split_sentences(chunk.content):
            cleaned = sentence.strip()
            if cleaned:
                chunk_sentences.append(cleaned)
            if len(chunk_sentences) >= max_sentences_per_chunk:
                break

        if chunk_sentences:
            sentences.extend(chunk_sentences)
            if idx not in used_chunk_indices:
                used_chunk_indices.append(idx)

        if len(sentences) >= max_sentences:
            break

    sentences = sentences[:max_sentences]

    answer = " ".join(sentences) if sentences else chunks[0].content.strip()
    if not used_chunk_indices and chunks:
        used_chunk_indices = [0]
    return SynthesisResult(
        answer=answer,
        why_this_matters="This answer is grounded in retrieved knowledge cards.",
        confidence=Confidence.medium,
        confidence_reason=None,
        used_chunk_indices=used_chunk_indices,
    )


def _parse_routing_category(value: str) -> RoutingCategory:
    mapping = {
        "hands-on engineering": RoutingCategory.hands_on_engineering,
        "architecture and system design": RoutingCategory.architecture_and_system_design,
        "ai and ml practice": RoutingCategory.ai_and_ml_practice,
        "leadership and product strategy": RoutingCategory.leadership_and_product_strategy,
        "research and academic credibility": RoutingCategory.research_and_academic_credibility,
        "career fit and role alignment": RoutingCategory.career_fit_and_role_alignment,
        "education and formal background": RoutingCategory.education_and_formal_background,
        "personal interests and working style": RoutingCategory.personal_interests_and_working_style,
    }
    normalized = (value or "").strip().lower()
    parsed = mapping.get(normalized)
    if parsed is not None:
        return parsed

    # Router drift observability: if the model starts returning slightly different
    # strings, we'd like to notice it during development without spamming prod.
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "unknown_routing_category_string",
            extra={
                "routing_category": value,
                "routing_category_normalized": normalized,
            },
        )
    return RoutingCategory.hands_on_engineering


def _parse_confidence(value: str) -> Confidence:
    lowered = value.strip().lower()
    if lowered == "high":
        return Confidence.high
    if lowered == "low":
        return Confidence.low
    return Confidence.medium


BANNED_WHY_PHRASES = (
    "crucial",
    "demonstrates",
    "aligns with",
    "highlights",
    "important to note",
    "enhances my ability",
)


# Regex variants used for detection after cleanup.
#
# Rationale:
# - General phrase removal below uses exact string matches (re.escape(phrase)).
# - If the model outputs inflected forms or punctuation variants (e.g.
#   "demonstrated", "demonstrating", "highlighted"), the exact removal may not
#   fully trigger.
# - We keep removal conservative, but detection broader so we can fall back to a
#   safe, neutral template when the output still contains boilerplate.
_BANNED_WHY_REGEXES = (
    r"\bcrucial\b",
    r"\bdemonstrat\w*\b",
    r"\balign\w*\s+with\b",
    r"\bhighlight\w*\b",
    r"\bimportant\w*\s+to\s+note\b",
    r"\benhanc\w*\s+my\s+ability\b",
)


_WHY_FALLBACKS: dict[str, tuple[str, ...]] = {
    RoutingCategory.hands_on_engineering.value: (
        "It affects how I build and debug production systems.",
        "It influences the trade-offs I make around reliability, maintainability, and delivery.",
    ),
    RoutingCategory.architecture_and_system_design.value: (
        "It shapes the trade-offs I make when designing system boundaries and keeping services operable over time.",
        "It affects long-term complexity and operability when scaling systems.",
    ),
    RoutingCategory.ai_and_ml_practice.value: (
        "It affects how I evaluate models and reduce failure modes in production.",
        "It changes how I balance model quality, cost, and reliability in real deployments.",
    ),
    RoutingCategory.leadership_and_product_strategy.value: (
        "It affects how I align stakeholders and make trade-offs that improve outcomes.",
        "It changes how I prioritize work and reduce execution risk for the team.",
    ),
    RoutingCategory.research_and_academic_credibility.value: (
        "It affects how rigorous my reasoning is when making technical claims.",
        "It supports credibility when discussing technical trade-offs and evidence.",
    ),
    RoutingCategory.education_and_formal_background.value: (
        "It gives a foundation I rely on when reasoning about systems and data.",
        "It provides background that shapes how I approach technical problems.",
    ),
    RoutingCategory.career_fit_and_role_alignment.value: (
        "It influences the kind of work I can deliver effectively in this role.",
        "It affects whether my experience matches the constraints and goals of the role.",
    ),
    RoutingCategory.personal_interests_and_working_style.value: (
        "It affects how I collaborate and stay effective over the long term.",
        "It influences day-to-day communication and how I work with a team.",
    ),
}


def _stable_choice(options: tuple[str, ...], *, seed: str) -> str:
    if not options:
        return ""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    idx = int.from_bytes(digest[:4], "big") % len(options)
    return options[idx]


def _normalize_routing_category(
    routing_category: str | RoutingCategory | None,
) -> str:
    if routing_category is None:
        return ""
    # RoutingCategory is a StrEnum, so str(routing_category) is already the human-readable label.
    return str(routing_category).strip()


def _fallback_why(*, routing_category: str | RoutingCategory | None, seed: str) -> str:
    category_key = _normalize_routing_category(routing_category)
    options = _WHY_FALLBACKS.get(category_key)
    if options:
        return _stable_choice(options, seed=f"{category_key}:{seed}")
    # Generic, modest fallback (used only for unknown category strings).
    generic = (
        "It affects how I make technical decisions.",
        "It influences practical trade-offs I make when building systems.",
    )
    return _stable_choice(generic, seed=seed)


def clean_why(why: str, routing_category: str | RoutingCategory | None = None) -> str:
    """Remove banned boilerplate while keeping output varied and category-aware.

    Strategy:
    - Prefer a soft clean: remove/trim banned phrases.
    - If the result becomes too short (or still contains banned phrases), use a
      neutral per-category fallback (chosen deterministically).
    """

    raw = (why or "").strip()
    if not raw:
        return _fallback_why(routing_category=routing_category, seed="empty")

    cleaned = raw

    # Targeted prefix cleanups to avoid leaving broken sentences.
    targeted_patterns: list[tuple[str, str]] = [
        (r"\bit is important to note that\s+", ""),
        (r"\bimportant to note that\s+", ""),
        (r"^(this|it)\s+demonstrates\s+", ""),
        (r"^(this|it)\s+highlights\s+", ""),
        (r"^(this|it)\s+aligns with\s+", ""),
        (r"^(this|it)\s+enhances my ability to\s+", ""),
        # Common artifacts after prefix removal (e.g. "This demonstrates that ...").
        (r"^that\s+", ""),
        # Avoid "to <verb> ..." fragments when the sentence lost its subject.
        (r"^to\s+", ""),
    ]
    for pattern, replacement in targeted_patterns:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE).strip()

    # General phrase removal (case-insensitive).
    for phrase in BANNED_WHY_PHRASES:
        cleaned = re.sub(re.escape(phrase), "", cleaned, flags=re.IGNORECASE)

    # Whitespace/punctuation cleanup.
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned).strip()
    cleaned = re.sub(r"^[\-–—:;,.\s]+", "", cleaned).strip()

    too_short = len(cleaned) < 18 or len(cleaned.split()) < 4
    still_banned = any(
        re.search(pattern, cleaned, flags=re.IGNORECASE)
        for pattern in _BANNED_WHY_REGEXES
    )
    if too_short or still_banned:
        return _fallback_why(routing_category=routing_category, seed=raw)

    return cleaned
