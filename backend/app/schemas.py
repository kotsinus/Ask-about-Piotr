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

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Category(str, Enum):
    hands_on_engineering = "Hands-on engineering"
    architecture_and_system_design = "Architecture and system design"
    ai_and_ml_practice = "AI and ML practice"
    leadership_and_product_strategy = "Leadership and product strategy"
    research_and_academic_credibility = "Research and academic credibility"
    career_fit_and_role_alignment = "Career fit and role alignment"


class Confidence(str, Enum):
    high = "High"
    medium = "Medium"
    low = "Low"


class EvidenceItem(BaseModel):
    snippet: str = Field(..., description="Quoted snippet from a retrieved chunk.")
    card_id: str = Field(..., description="Card identifier for the snippet source.")


class SourceRef(BaseModel):
    card_id: str = Field(..., description="Card identifier.")
    section: str = Field(..., description="Section name inside the card.")


class ConversationContext(BaseModel):
    conversation_id: Optional[str] = Field(
        None, description="Client-provided conversation identifier."
    )
    last_topic: Optional[str] = Field(
        None, description="Last resolved topic used for follow-up questions."
    )


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"] = Field(
        ..., description="Message author role."
    )
    content: str = Field(..., min_length=1, description="Message content.")


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="User question.")
    messages: Optional[List[ChatMessage]] = Field(
        None,
        description=(
            "Optional conversation history (typically last N turns). "
            "When provided, the backend may rewrite follow-up questions into a "
            "standalone question before retrieval."
        ),
    )
    context: Optional[ConversationContext] = Field(
        None,
        description="Optional conversation context for follow-up questions.",
    )


class ChatResponse(BaseModel):
    category: Category
    answer: str
    why_this_matters: str
    evidence: List[EvidenceItem]
    sources: List[SourceRef]
    confidence: Confidence
    confidence_reason: Optional[str] = None
    context: Optional[ConversationContext] = None
    formatted_answer: str = Field(
        ...,
        description="User-facing answer formatted per the mandatory template.",
    )

