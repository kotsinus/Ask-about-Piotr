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
    question: str, limit: int = 5, conversation_topic: Optional[str] = None
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
                ORDER BY distance
                LIMIT %s;
                """,
                (embedding_text, max(limit * 3, 10)),
            )
            rows = cursor.fetchall()

    if not rows:
        return []

    top_card_id = rows[0][0]
    filtered = [row for row in rows if row[0] == top_card_id][:limit]
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

