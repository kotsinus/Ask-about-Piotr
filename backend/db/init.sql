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
    card_category TEXT NOT NULL,
    section TEXT NOT NULL,
    source_url TEXT,
    content TEXT NOT NULL,
    embedding vector(1536)
);

-- Backward-compatible schema evolution (for existing DB volumes).
-- CREATE TABLE IF NOT EXISTS does NOT add new columns.
ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS card_category TEXT;

CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
    ON knowledge_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Privacy-first logging of user interactions (question + final answer) and
-- anonymized client metadata.
--
-- MUST NOT contain raw IP addresses.
CREATE TABLE IF NOT EXISTS interaction_logs (
    id BIGSERIAL PRIMARY KEY,
    request_id TEXT NOT NULL,
    session_id TEXT,
    conversation_id TEXT,
    request_at TIMESTAMPTZ NOT NULL,
    response_at TIMESTAMPTZ NOT NULL,
    latency_ms DOUBLE PRECISION,
    question TEXT NOT NULL,
    standalone_question TEXT,
    answer TEXT NOT NULL,
    router_model TEXT,
    synthesis_model TEXT,
    embeddings_provider TEXT,
    embeddings_model TEXT,
    incoming_last_topic TEXT,
    resolved_topic TEXT,
    topic_used_for_retrieval BOOLEAN,
    messages_count INTEGER,
    retrieval_chunk_count INTEGER,
    llm_context_messages JSONB,
    ip_prefix TEXT,
    ip_hash TEXT,
    user_agent TEXT,
    country TEXT,
    logged_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Backward-compatible schema evolution (for existing DB volumes).
-- CREATE TABLE IF NOT EXISTS does NOT add new columns.
ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS session_id TEXT;

ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS conversation_id TEXT;

ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS standalone_question TEXT;

ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS incoming_last_topic TEXT;

ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS resolved_topic TEXT;

ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS topic_used_for_retrieval BOOLEAN;

ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS messages_count INTEGER;

ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS retrieval_chunk_count INTEGER;

ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS llm_context_messages JSONB;

CREATE INDEX IF NOT EXISTS interaction_logs_logged_at_idx
    ON interaction_logs (logged_at);

CREATE INDEX IF NOT EXISTS interaction_logs_request_id_idx
    ON interaction_logs (request_id);

CREATE INDEX IF NOT EXISTS interaction_logs_session_id_idx
    ON interaction_logs (session_id);

CREATE INDEX IF NOT EXISTS interaction_logs_conversation_id_idx
    ON interaction_logs (conversation_id);

CREATE INDEX IF NOT EXISTS interaction_logs_ip_prefix_idx
    ON interaction_logs (ip_prefix);

CREATE INDEX IF NOT EXISTS interaction_logs_ip_hash_idx
    ON interaction_logs (ip_hash);

