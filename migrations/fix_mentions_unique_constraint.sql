-- ====================================
-- MIGRATION: Fix Unique Constraint on Mentions
-- ====================================
-- This migration changes the uniqueness constraint on the mentions table.
-- Previously, 'post_link' was globally unique, preventing multiple users/brands
-- from tracking the same article.
--
-- New Logic: A link must be unique per TOPIC only.
-- This allows:
-- 1. Multiple brands to track the same article.
-- 2. The same brand to track the same article under different topics (if desired).

-- 1. Drop the old global unique constraint
ALTER TABLE mentions DROP CONSTRAINT IF EXISTS mentions_post_link_key;

-- 2. Add the new composite unique constraint (post_link + topic_id)
-- Note: We use topic_id because it is the most granular level.
-- Since a Topic belongs to a Brand, this automatically ensures per-Brand uniqueness as well.
ALTER TABLE mentions ADD CONSTRAINT mentions_post_link_topic_id_key UNIQUE (post_link, topic_id);

-- 3. Verify the change (Optional comment for logs)
COMMENT ON CONSTRAINT mentions_post_link_topic_id_key ON mentions IS 'Ensures articles are unique per topic, allowing multiple brands/users to track the same URL.';
