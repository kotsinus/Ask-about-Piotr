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

"""Retrieval over knowledge chunks using pgvector."""

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
# Executes similarity search over knowledge chunks using pgvector.
#
# Notes:
# Embeddings are required; the stub provider will raise until configured.

from __future__ import annotations

from typing import List, Optional

import psycopg
from pgvector.psycopg import register_vector
from pydantic import BaseModel

from app.config import get_settings
from app.embeddings import get_embedding_provider


class RetrievedChunk(BaseModel):
    card_id: str
    category: str
    section: str
    source_url: str | None = None
    content: str


def retrieve(
    question: str, limit: int = 25, conversation_topic: Optional[str] = None
) -> List[RetrievedChunk]:
    """Retrieve relevant chunks for a question using pgvector."""

    settings = get_settings()
    retrieval_query = (
        f"{question}\n\nConversation topic: {conversation_topic}"
        if conversation_topic
        else question
    )
    provider = get_embedding_provider(
        name=settings.embeddings_provider,
        dimensions=settings.embeddings_dimensions,
    )
    embedding = provider.embed([retrieval_query])[0]
    embedding_text = "[" + ",".join(str(value) for value in embedding) + "]"

    # We may skip many highly-similar chunks from a single card to allow evidence
    # to come from multiple cards. Fetch a larger candidate set to keep recall.
    candidate_limit = max(limit * 8, 30)

    with psycopg.connect(settings.database_url) as conn:
        register_vector(conn)
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL enable_indexscan = off;")
            cursor.execute("SET LOCAL enable_bitmapscan = off;")
            cursor.execute(
                """
                SELECT card_id, category, section, source_url, content,
                       embedding <=> %s::vector AS distance
                FROM knowledge_chunks
                WHERE section <> 'Links'
                ORDER BY distance
                LIMIT %s;
                """,
                (embedding_text, candidate_limit),
            )
            rows = cursor.fetchall()

    if not rows:
        return []

    # Diversify lightly across cards: keep similarity ordering, but avoid returning
    # too many chunks from a single card when other relevant cards are present.
    per_card_cap = 2
    selected: list[tuple] = []
    per_card_counts: dict[str, int] = {}

    for row in rows:
        card_id = row[0]
        if per_card_counts.get(card_id, 0) >= per_card_cap:
            continue
        selected.append(row)
        per_card_counts[card_id] = per_card_counts.get(card_id, 0) + 1
        if len(selected) >= limit:
            break

    # If diversification was too strict (e.g., only one card exists), fill the
    # remaining slots without the per-card cap.
    if len(selected) < limit:
        selected_set = {id(row) for row in selected}
        for row in rows:
            if id(row) in selected_set:
                continue
            selected.append(row)
            if len(selected) >= limit:
                break

    filtered = selected[:limit]
    return [
        RetrievedChunk(
            card_id=row[0],
            category=row[1],
            section=row[2],
            source_url=row[3],
            content=row[4],
        )
        for row in filtered
    ]

