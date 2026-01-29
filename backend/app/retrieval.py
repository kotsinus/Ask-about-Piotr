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
# Defines retrieval interfaces and an in-memory stub for RAG.
#
# Notes:
# Replace with vector-store backed retrieval when knowledge cards are added.

from __future__ import annotations

from typing import List

from pydantic import BaseModel


class RetrievedChunk(BaseModel):
    card_id: str
    category: str
    section: str
    source_url: str | None = None
    content: str


def retrieve(question: str) -> List[RetrievedChunk]:
    """Retrieve relevant chunks for a question.

    TODO: Replace with vector-store backed retrieval over knowledge cards.
    """

    _ = question
    return []

