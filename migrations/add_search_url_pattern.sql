-- Migration: Add search_url_pattern to source_configs table
-- Date: 2025-12-23
-- Description: Adds auto-detected search URL pattern to source configurations

-- Add search_url_pattern column
ALTER TABLE source_configs
ADD COLUMN IF NOT EXISTS search_url_pattern TEXT;

-- Add comment explaining the column
COMMENT ON COLUMN source_configs.search_url_pattern IS
'The URL pattern to search for keywords. Example: https://domain.com/search?q={keyword}. The {keyword} placeholder will be replaced with actual search terms.';

-- Optional: Add index for better query performance
CREATE INDEX IF NOT EXISTS idx_source_configs_search_pattern
ON source_configs(domain)
WHERE search_url_pattern IS NOT NULL;
