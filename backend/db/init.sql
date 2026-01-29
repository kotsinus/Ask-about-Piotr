-- Copyright 2026 Piotr Synak
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Purpose:
-- Initializes the pgvector schema for knowledge card chunks.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id SERIAL PRIMARY KEY,
    card_id TEXT NOT NULL,
    category TEXT NOT NULL,
    section TEXT NOT NULL,
    source_url TEXT,
    content TEXT NOT NULL,
    embedding vector(1536)
);

CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
    ON knowledge_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

