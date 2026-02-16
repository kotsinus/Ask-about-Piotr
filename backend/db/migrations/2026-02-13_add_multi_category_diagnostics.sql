-- Copyright 2026 Piotr Synak
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Purpose:
-- Forward-only, idempotent migration for multi-category routing diagnostics.
-- Adds JSONB columns for routing, retrieval, and quality gate data.
--
-- Safe to run multiple times.

-- Routing result: categories, budgets, confidence, fallback flag
ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS routing JSONB;

-- Per-category retrieval stats: counts, budgets, selected chunks
ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS retrieval_by_category JSONB;

-- Quality gate results: passed, failure_reasons, retry_attempted
ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS quality_gate JSONB;

-- Create GIN indexes for JSONB query performance
CREATE INDEX IF NOT EXISTS interaction_logs_routing_idx
    ON interaction_logs USING GIN (routing);

CREATE INDEX IF NOT EXISTS interaction_logs_retrieval_by_category_idx
    ON interaction_logs USING GIN (retrieval_by_category);

CREATE INDEX IF NOT EXISTS interaction_logs_quality_gate_idx
    ON interaction_logs USING GIN (quality_gate);
