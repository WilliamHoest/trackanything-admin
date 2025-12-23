-- Migration: Add content_teaser to mentions table
ALTER TABLE mentions ADD COLUMN IF NOT EXISTS content_teaser TEXT DEFAULT NULL;
