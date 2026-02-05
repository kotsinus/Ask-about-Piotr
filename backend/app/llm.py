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

import json
import re
from dataclasses import dataclass

from openai import OpenAI

from app.config import get_settings
from app.retrieval import RetrievedChunk
from app.schemas import Category, Confidence


def rewrite_question(question: str, messages: list[dict] | None = None) -> str:
    """Rewrite a potentially ambiguous follow-up question into a standalone question.

    - Preserves user intent and meaning.
    - Resolves pronouns/ellipses using provided history.
    - Avoids adding new facts.
    - Keeps the result concise.

    If no OpenAI API key is configured, returns the original question.
    """

    if not messages:
        return question

    settings = get_settings()
    if not settings.openai_api_key:
        return question

    # Keep last few turns to limit token use.
    trimmed = messages[-6:]

    client = OpenAI(api_key=settings.openai_api_key)
    system_prompt = (
        "You rewrite the user's latest question into a standalone question. "
        "Use the conversation history only to resolve references (pronouns, "
        "ellipsis, omitted subject). Do NOT add facts or assumptions not present "
        'in the history. Keep it concise. Return JSON: {"standalone_question": "..."}.'
    )
    user_prompt = (
        "Conversation history (chronological):\n"
        + "\n".join(f"{m.get('role', '')}: {m.get('content', '')}" for m in trimmed)
        + "\n\nLatest user question:\n"
        + question
    )

    response = client.chat.completions.create(
        model=settings.synthesis_model,
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
        return question

    rewritten = str(payload.get("standalone_question", "")).strip()
    return rewritten or question


@dataclass(frozen=True)
class SynthesisResult:
    answer: str
    why_this_matters: str
    confidence: Confidence
    confidence_reason: str | None
    used_chunk_indices: list[int]


def route_category(question: str) -> Category:
    """Route a question into exactly one category using a low-cost model."""

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for routing.")

    client = OpenAI(api_key=settings.openai_api_key)
    system_prompt = (
        "Classify the question into exactly one category from this list: "
        "Hands-on engineering, Architecture and system design, AI and ML practice, "
        "Leadership and product strategy, Research and academic credibility, "
        'Career fit and role alignment. Return JSON: {"category": "..."}.'
    )

    response = client.chat.completions.create(
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
    return _parse_category(payload.get("category", ""))


def synthesize_answer(
    question: str,
    chunks: list[RetrievedChunk],
    conversation_topic: str | None = None,
    conversation_messages: list[dict] | None = None,
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

    client = OpenAI(api_key=settings.openai_api_key)
    evidence_lines = [
        f"[{idx}] [{chunk.card_id}.{chunk.section}] {chunk.content}"
        for idx, chunk in enumerate(chunks)
    ]
    system_prompt = (
        "You answer only using the provided evidence. "
        "Conversation context may be provided only to help interpret the question; "
        "it is NOT evidence and must not override or add to the evidence. "
        "You MUST NOT return answers that consist of only 'Yes', 'No', "
        "or a single sentence. "
        "For yes/no questions, the answer field MUST contain: "
        "(1) a clear yes/no statement, "
        "(2) justification grounded explicitly in the evidence, "
        "(3) an explanation of why the cited evidence supports the answer. "
        "The 'answer' field MUST contain at least 40 words unless the refusal message is used. "
        "If evidence is insufficient to justify an answer, you MUST respond "
        "with the exact refusal message and nothing else. "
        "If you use evidence, you MUST list which evidence items were used "
        "via their indices. "
        "Return JSON with the following fields only: "
        '{"answer", "why_this_matters", "confidence", "confidence_reason", "used_chunk_indices"}. '
        "Use confidence values: High, Medium, or Low. "
        "The refusal message is exactly: "
        '"I do not have enough evidence in the provided materials."'
    )
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
        f"{question}\n\n"
        + context_block
        + topic_line
        + "Evidence:\n"
        + "\n".join(evidence_lines)
    )

    response = client.chat.completions.create(
        model=settings.synthesis_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    content = response.choices[0].message.content or "{}"
    payload = json.loads(content)

    answer = str(payload.get("answer", "")).strip()
    if not answer:
        return _fallback_synthesis(chunks)

    refusal = "I do not have enough evidence in the provided materials."
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


def _parse_category(value: str) -> Category:
    mapping = {
        "hands-on engineering": Category.hands_on_engineering,
        "architecture and system design": Category.architecture_and_system_design,
        "ai and ml practice": Category.ai_and_ml_practice,
        "leadership and product strategy": Category.leadership_and_product_strategy,
        "research and academic credibility": Category.research_and_academic_credibility,
        "career fit and role alignment": Category.career_fit_and_role_alignment,
    }
    return mapping.get(value.strip().lower(), Category.hands_on_engineering)


def _parse_confidence(value: str) -> Confidence:
    lowered = value.strip().lower()
    if lowered == "high":
        return Confidence.high
    if lowered == "low":
        return Confidence.low
    return Confidence.medium
