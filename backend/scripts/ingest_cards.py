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

import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

REPO_ROOT = BACKEND_ROOT.parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _normalize_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if parsed.hostname != "db":
        return database_url
    if Path("/.dockerenv").exists() or os.environ.get("IN_DOCKER") == "1":
        return database_url
    netloc = parsed.netloc.replace("db", "localhost")
    return urlunparse(parsed._replace(netloc=netloc))


def _ensure_database_exists(database_url: str) -> None:
    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip("/")
    if not db_name:
        return

    admin_url = urlunparse(parsed._replace(path="/postgres"))
    with psycopg.connect(admin_url, autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            exists = cursor.fetchone()
            if not exists:
                cursor.execute(f"CREATE DATABASE {db_name}")


from app.config import get_settings
from app.embeddings import get_embedding_provider
from app.knowledge import chunk_cards, load_cards


def main() -> None:
    _load_env_file(REPO_ROOT / ".env")
    settings = get_settings()
    database_url = _normalize_database_url(settings.database_url)
    _ensure_database_exists(database_url)
    provider = get_embedding_provider(
        name=settings.embeddings_provider,
        dimensions=settings.embeddings_dimensions,
    )

    knowledge_dir = Path(__file__).resolve().parents[2] / "knowledge"
    cards = load_cards(knowledge_dir)
    chunks = chunk_cards(cards)

    embeddings = provider.embed([chunk.content for chunk in chunks])

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id SERIAL PRIMARY KEY,
                    card_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    section TEXT NOT NULL,
                    source_url TEXT,
                    content TEXT NOT NULL,
                    embedding vector(1536)
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
                    ON knowledge_chunks
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100);
                """
            )
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
