-- Copyright 2026 Piotr Synak
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Purpose:
-- Forward-only, idempotent migration to add JSONB payload columns for
-- multi-category routing / retrieval observability.
--
-- Safe to run multiple times.

ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS routing JSONB;

ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS retrieval_by_category JSONB;

ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS quality_gate JSONB;
