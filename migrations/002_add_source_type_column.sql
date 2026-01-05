-- =========================================================
-- Migration: Add source_type column to semantic_memory
-- =========================================================
-- Run this if your database was created before source_type was added

BEGIN;

-- Add source_type column if it doesn't exist
ALTER TABLE semantic_memory 
ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'manual';

-- Create index for faster filtering
CREATE INDEX IF NOT EXISTS idx_semantic_memory_source_type 
ON semantic_memory(source_type);

-- Update existing rows to have a default source_type if NULL
UPDATE semantic_memory 
SET source_type = 'manual' 
WHERE source_type IS NULL;

COMMIT;

