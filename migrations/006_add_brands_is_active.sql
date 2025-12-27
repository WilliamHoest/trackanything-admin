-- Migration: Add is_active and last_scraped_at fields to brands table
-- This enables users to keep brands but disable them from scraping
-- and tracks when each brand was last scraped

-- Add is_active column
ALTER TABLE brands ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

-- Add last_scraped_at column (critical for preventing constant scraping)
ALTER TABLE brands ADD COLUMN IF NOT EXISTS last_scraped_at TIMESTAMPTZ DEFAULT NULL;

-- Add comments for documentation
COMMENT ON COLUMN brands.is_active IS 'Whether this brand is active for scraping';
COMMENT ON COLUMN brands.last_scraped_at IS 'Timestamp of last scrape attempt (regardless of whether mentions were found)';

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_brands_is_active ON brands(is_active);
CREATE INDEX IF NOT EXISTS idx_brands_last_scraped ON brands(last_scraped_at);
