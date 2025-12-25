-- Add scrape_frequency_hours column to brands table
ALTER TABLE brands
ADD COLUMN IF NOT EXISTS scrape_frequency_hours INTEGER DEFAULT 24;

-- Add comment
COMMENT ON COLUMN brands.scrape_frequency_hours IS 'Frequency of scraping in hours (e.g., 1, 4, 24, 168)';
