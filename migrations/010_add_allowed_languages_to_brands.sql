-- Migration 010: Add allowed_languages to brands table
-- Allows per-brand language filtering in the scraping pipeline.
-- NULL = use global default from settings (SCRAPING_DEFAULT_LANGUAGES).

ALTER TABLE brands
    ADD COLUMN IF NOT EXISTS allowed_languages TEXT[] DEFAULT NULL;
