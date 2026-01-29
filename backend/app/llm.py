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

import re
import json
from dataclasses import dataclass
from typing import List

from openai import OpenAI

from app.config import get_settings
from app.retrieval import RetrievedChunk
from app.schemas import Category, Confidence


@dataclass(frozen=True)
class SynthesisResult:
    answer: str
    why_this_matters: str
    confidence: Confidence
    confidence_reason: str | None


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
        "Career fit and role alignment. Return JSON: {\"category\": \"...\"}."
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


def synthesize_answer(question: str, chunks: List[RetrievedChunk]) -> SynthesisResult:
    """Generate a strict, grounded answer from retrieved chunks."""

    if not chunks:
        return SynthesisResult(
            answer="I do not have enough evidence in the provided materials.",
            why_this_matters=(
                "The system must cite retrieved knowledge cards, and none were found."
            ),
            confidence=Confidence.low,
            confidence_reason="No relevant knowledge cards were retrieved for this question.",
        )

    settings = get_settings()
    if not settings.openai_api_key:
        return _fallback_synthesis(chunks)

    client = OpenAI(api_key=settings.openai_api_key)
    evidence_lines = [
        f"[{chunk.card_id}.{chunk.section}] {chunk.content}" for chunk in chunks
    ]
    system_prompt = (
        "You answer only using the provided evidence. "
        "If evidence is insufficient, respond with the exact refusal message. "
        "Return JSON: {\"answer\", \"why_this_matters\", \"confidence\", "
        "\"confidence_reason\"}. Use confidence High/Medium/Low."
    )
    user_prompt = (
        "Question:\n"
        f"{question}\n\n"
        "Evidence:\n"
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
    )


def _split_sentences(text: str) -> List[str]:
    return [segment for segment in re.split(r"(?<=[.!?])\s+", text) if segment]


def _fallback_synthesis(chunks: List[RetrievedChunk]) -> SynthesisResult:
    sentences: List[str] = []
    for chunk in chunks:
        for sentence in _split_sentences(chunk.content):
            cleaned = sentence.strip()
            if cleaned:
                sentences.append(cleaned)
                break
        if len(sentences) >= 6:
            break

    answer = " ".join(sentences) if sentences else chunks[0].content.strip()
    return SynthesisResult(
        answer=answer,
        why_this_matters="This answer is grounded in retrieved knowledge cards.",
        confidence=Confidence.medium,
        confidence_reason=None,
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

