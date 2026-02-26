-- Add discovery strategy fields to source_configs
-- Enables RSS, sitemap, and site_search discovery per source

ALTER TABLE source_configs
  ADD COLUMN IF NOT EXISTS rss_urls       text[]  DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS sitemap_url    text    DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS discovery_type text    DEFAULT 'site_search'
    CHECK (discovery_type IN ('rss', 'sitemap', 'site_search'));

COMMENT ON COLUMN source_configs.rss_urls       IS 'RSS feed URLs for this source (array, used when discovery_type=rss)';
COMMENT ON COLUMN source_configs.sitemap_url    IS 'News sitemap URL for this source (used when discovery_type=sitemap)';
COMMENT ON COLUMN source_configs.discovery_type IS 'Discovery strategy: rss | sitemap | site_search (default)';
