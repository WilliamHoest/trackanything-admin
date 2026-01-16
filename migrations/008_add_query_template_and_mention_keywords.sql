-- ====================================
-- MIGRATION: Topic query templates + mention keyword links
-- ====================================

ALTER TABLE topics
ADD COLUMN IF NOT EXISTS query_template TEXT;

ALTER TABLE mentions
ADD COLUMN IF NOT EXISTS primary_keyword_id BIGINT REFERENCES keywords(id);

CREATE TABLE IF NOT EXISTS mention_keywords (
    mention_id BIGINT NOT NULL REFERENCES mentions(id) ON DELETE CASCADE,
    keyword_id BIGINT NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
    matched_in TEXT,
    score INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (mention_id, keyword_id)
);

CREATE INDEX IF NOT EXISTS idx_mention_keywords_mention_id ON mention_keywords(mention_id);
CREATE INDEX IF NOT EXISTS idx_mention_keywords_keyword_id ON mention_keywords(keyword_id);

ALTER TABLE mention_keywords ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own mention keywords" ON mention_keywords
    FOR SELECT USING (
        auth.uid() IN (
            SELECT b.profile_id
            FROM mentions m
            JOIN brands b ON m.brand_id = b.id
            WHERE m.id = mention_keywords.mention_id
        )
    );

CREATE POLICY "Users can insert own mention keywords" ON mention_keywords
    FOR INSERT WITH CHECK (
        auth.uid() IN (
            SELECT b.profile_id
            FROM mentions m
            JOIN brands b ON m.brand_id = b.id
            WHERE m.id = mention_keywords.mention_id
        )
    );

CREATE POLICY "Users can delete own mention keywords" ON mention_keywords
    FOR DELETE USING (
        auth.uid() IN (
            SELECT b.profile_id
            FROM mentions m
            JOIN brands b ON m.brand_id = b.id
            WHERE m.id = mention_keywords.mention_id
        )
    );
