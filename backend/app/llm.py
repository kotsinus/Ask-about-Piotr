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
from dataclasses import dataclass
from typing import List

from app.retrieval import RetrievedChunk
from app.schemas import Confidence


@dataclass(frozen=True)
class SynthesisResult:
    answer: str
    why_this_matters: str
    confidence: Confidence
    confidence_reason: str | None


def synthesize_answer(question: str, chunks: List[RetrievedChunk]) -> SynthesisResult:
    """Generate a strict, grounded answer from retrieved chunks.

    The answer must not introduce facts beyond the evidence. This implementation
    extracts sentences directly from retrieved content.
    """

    if not chunks:
        return SynthesisResult(
            answer="I do not have enough evidence in the provided materials.",
            why_this_matters=(
                "The system must cite retrieved knowledge cards, and none were found."
            ),
            confidence=Confidence.low,
            confidence_reason="No relevant knowledge cards were retrieved for this question.",
        )

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
    why_this_matters = "This answer is grounded in retrieved knowledge cards."

    return SynthesisResult(
        answer=answer,
        why_this_matters=why_this_matters,
        confidence=Confidence.medium,
        confidence_reason=None,
    )


def _split_sentences(text: str) -> List[str]:
    return [segment for segment in re.split(r"(?<=[.!?])\s+", text) if segment]

