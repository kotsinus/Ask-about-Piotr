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

from typing import List

from fastapi import FastAPI

from app.retrieval import retrieve
from app.schemas import (
    Category,
    ChatRequest,
    ChatResponse,
    Confidence,
    EvidenceItem,
    SourceRef,
)
from app.llm import route_category, synthesize_answer

app = FastAPI(title="Ask about Piotr API", version="0.1.0")


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
    evidence: List[EvidenceItem],
    sources: List[SourceRef],
    confidence: Confidence,
    confidence_reason: str | None,
) -> str:
    evidence_lines = (
        [f"- \"{item.snippet}\" ({item.card_id})" for item in evidence]
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
        "Evidence:\n"
        + "\n".join(evidence_lines)
        + "\n\n"
        "Sources:\n"
        + "\n".join(source_lines)
        + "\n\n"
        "Confidence:\n"
        + confidence_line
    )


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        category = route_category(request.question)
    except Exception:
        category = classify_question(request.question)
    chunks = retrieve(request.question)

    evidence = [
        EvidenceItem(snippet=chunk.content, card_id=chunk.card_id)
        for chunk in chunks
    ]
    sources = [SourceRef(card_id=chunk.card_id, section=chunk.section) for chunk in chunks]
    synthesis = synthesize_answer(request.question, chunks)

    response = ChatResponse(
        category=category,
        answer=synthesis.answer,
        why_this_matters=synthesis.why_this_matters,
        evidence=evidence,
        sources=sources,
        confidence=synthesis.confidence,
        confidence_reason=synthesis.confidence_reason,
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
    return response

