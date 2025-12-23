-- AI-Assisted Source Configuration Table Migration
-- This table stores CSS selectors for scraping specific domains
-- Created: 2025-12-23

-- Create source_configs table
CREATE TABLE source_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain VARCHAR(255) UNIQUE NOT NULL,
    title_selector VARCHAR(500),
    content_selector VARCHAR(500),
    date_selector VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index on domain for faster lookups
CREATE INDEX idx_source_configs_domain ON source_configs(domain);

-- Enable Row Level Security
ALTER TABLE source_configs ENABLE ROW LEVEL SECURITY;

-- RLS Policies for source_configs (Admin-only table - all authenticated users can read)
CREATE POLICY "Authenticated users can view source configs" ON source_configs
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can insert source configs" ON source_configs
    FOR INSERT TO authenticated WITH CHECK (true);

CREATE POLICY "Authenticated users can update source configs" ON source_configs
    FOR UPDATE TO authenticated USING (true);

CREATE POLICY "Authenticated users can delete source configs" ON source_configs
    FOR DELETE TO authenticated USING (true);

-- Create function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_source_configs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update updated_at on row update
CREATE TRIGGER trigger_update_source_configs_updated_at
    BEFORE UPDATE ON source_configs
    FOR EACH ROW
    EXECUTE FUNCTION update_source_configs_updated_at();

-- Add comment to table
COMMENT ON TABLE source_configs IS 'Stores CSS selector configurations for scraping specific domains';
COMMENT ON COLUMN source_configs.domain IS 'Domain name (e.g., berlingske.dk)';
COMMENT ON COLUMN source_configs.title_selector IS 'CSS selector for article title';
COMMENT ON COLUMN source_configs.content_selector IS 'CSS selector for article content';
COMMENT ON COLUMN source_configs.date_selector IS 'CSS selector for publication date';
