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
# Loads markdown knowledge cards and writes chunks into Postgres.
#
# Notes:
# Requires a configured embeddings provider; the stub will raise.

from __future__ import annotations

from pathlib import Path

import psycopg

from app.config import get_settings
from app.embeddings import get_embedding_provider
from app.knowledge import chunk_cards, load_cards


def main() -> None:
    settings = get_settings()
    provider = get_embedding_provider(
        name=settings.embeddings_provider,
        dimensions=settings.embeddings_dimensions,
    )

    knowledge_dir = Path(__file__).resolve().parents[2] / "knowledge"
    cards = load_cards(knowledge_dir)
    chunks = chunk_cards(cards)

    embeddings = provider.embed([chunk.content for chunk in chunks])

    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE knowledge_chunks;")
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                cursor.execute(
                    """
                    INSERT INTO knowledge_chunks
                        (card_id, category, section, source_url, content, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """,
                    (
                        chunk.card_id,
                        chunk.category,
                        chunk.section,
                        chunk.source_url,
                        chunk.content,
                        embedding,
                    ),
                )
        conn.commit()


if __name__ == "__main__":
    main()

