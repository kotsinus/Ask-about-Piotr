-- Copyright 2026 Piotr Synak
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Purpose:
-- Forward-only, idempotent migration for production databases created before
-- interaction_logs context columns were added.
--
-- Safe to run multiple times.

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

