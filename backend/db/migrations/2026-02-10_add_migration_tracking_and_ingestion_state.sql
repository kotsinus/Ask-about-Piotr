-- Copyright 2026 Piotr Synak
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Purpose:
-- Add tracking tables used by the lightweight migration runner and by
-- knowledge auto-ingestion change detection.
--
-- Notes:
-- - Must be safe to re-run.

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    checksum_sha256 TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Singleton table: exactly one row (id=1) tracks the latest ingestion inputs.
CREATE TABLE IF NOT EXISTS knowledge_ingestion_state (
    id INTEGER PRIMARY KEY,
    knowledge_hash_sha256 TEXT NOT NULL,
    embeddings_provider TEXT NOT NULL,
    embeddings_model TEXT,
    embeddings_dimensions INTEGER NOT NULL,
    cards_count INTEGER,
    chunks_count INTEGER,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

