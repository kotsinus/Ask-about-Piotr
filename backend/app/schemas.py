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
# Defines API request/response schemas and strict answer format fields.
#
# Notes:
# Keep this file as the single source of truth for response contracts.

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Category(StrEnum):
    hands_on_engineering = "Hands-on engineering"
    architecture_and_system_design = "Architecture and system design"
    ai_and_ml_practice = "AI and ML practice"
    leadership_and_product_strategy = "Leadership and product strategy"
    research_and_academic_credibility = "Research and academic credibility"
    career_fit_and_role_alignment = "Career fit and role alignment"
    education_and_formal_background = "Education and formal background"
    personal_interests_and_working_style = "Personal interests and working style"


class Confidence(StrEnum):
    high = "High"
    medium = "Medium"
    low = "Low"


class EvidenceItem(BaseModel):
    snippet: str = Field(..., description="Quoted snippet from a retrieved chunk.")
    card_id: str = Field(..., description="Card identifier for the snippet source.")


class SourceRef(BaseModel):
    card_id: str = Field(..., description="Card identifier.")
    section: str = Field(..., description="Section name inside the card.")


class DebugRetrievalItem(BaseModel):
    card_id: str
    section: str
    distance: float


class RoutingCategoryItem(BaseModel):
    category: Category
    confidence: str
    budget: int


class RoutingResult(BaseModel):
    categories: list[RoutingCategoryItem]


class ConversationContext(BaseModel):
    conversation_id: str | None = Field(
        None, description="Client-provided conversation identifier."
    )
    last_topic: str | None = Field(
        None, description="Last resolved topic used for follow-up questions."
    )


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"] = Field(..., description="Message author role.")
    content: str = Field(..., min_length=1, description="Message content.")


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="User question.")
    messages: list[ChatMessage] | None = Field(
        None,
        description=(
            "Optional conversation history (typically last N turns). "
            "When provided, the backend may rewrite follow-up questions into a "
            "standalone question before retrieval."
        ),
    )
    context: ConversationContext | None = Field(
        None,
        description="Optional conversation context for follow-up questions.",
    )


class ChatResponse(BaseModel):
    category: Category
    answer: str
    why_this_matters: str
    evidence: list[EvidenceItem]
    sources: list[SourceRef]
    debug_retrieval: list[DebugRetrievalItem] | None = None
    routing: RoutingResult | None = None
    confidence: Confidence
    confidence_reason: str | None = None
    context: ConversationContext | None = None
    formatted_answer: str = Field(
        ...,
        description="User-facing answer formatted per the mandatory template.",
    )
