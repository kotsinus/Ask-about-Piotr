-- Copyright 2026 Piotr Synak
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Purpose:
-- Introduce unambiguous content taxonomy column name `card_category`.
--
-- Notes:
-- - Idempotent (safe on repeated runs).
-- - Backfills from legacy `category` when present.
-- - Drops legacy `category` column after backfill.

ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS card_category TEXT;

-- Backfill from legacy `category` column if it exists and has data.
-- This is safe to run multiple times; only updates where card_category is NULL.
UPDATE knowledge_chunks
SET card_category = category
WHERE card_category IS NULL
  AND category IS NOT NULL;

-- Ensure card_category is NOT NULL (consistent with card loader expectations).
-- Only apply if column exists and not already NOT NULL.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'knowledge_chunks'
          AND column_name = 'card_category'
          AND is_nullable = 'YES'
    ) THEN
        ALTER TABLE knowledge_chunks ALTER COLUMN card_category SET NOT NULL;
    END IF;
END $$;

-- Drop legacy `category` column if it exists.
ALTER TABLE knowledge_chunks
    DROP COLUMN IF EXISTS category;
