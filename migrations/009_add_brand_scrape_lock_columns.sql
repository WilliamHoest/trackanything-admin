-- Migration: Add per-brand scrape lock columns to prevent overlapping runs

ALTER TABLE brands
ADD COLUMN IF NOT EXISTS scrape_in_progress BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE brands
ADD COLUMN IF NOT EXISTS scrape_started_at TIMESTAMPTZ DEFAULT NULL;

-- Safety for existing rows
UPDATE brands
SET scrape_in_progress = FALSE
WHERE scrape_in_progress IS NULL;

CREATE INDEX IF NOT EXISTS idx_brands_scrape_in_progress
ON brands(scrape_in_progress);

CREATE INDEX IF NOT EXISTS idx_brands_scrape_started_at
ON brands(scrape_started_at);

COMMENT ON COLUMN brands.scrape_in_progress IS 'True while a scrape job is running for this brand';
COMMENT ON COLUMN brands.scrape_started_at IS 'UTC timestamp when current scrape lock was acquired';
