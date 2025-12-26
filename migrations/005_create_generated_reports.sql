-- Create generated_reports table
CREATE TABLE IF NOT EXISTS generated_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    brand_id BIGINT REFERENCES brands(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    report_type TEXT NOT NULL CHECK (report_type IN ('weekly', 'crisis', 'summary', 'custom')),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS
ALTER TABLE generated_reports ENABLE ROW LEVEL SECURITY;

-- Policies for generated_reports
CREATE POLICY "Users can view their own reports"
    ON generated_reports FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own reports"
    ON generated_reports FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own reports"
    ON generated_reports FOR DELETE
    USING (auth.uid() = user_id);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_generated_reports_user_id ON generated_reports(user_id);
CREATE INDEX IF NOT EXISTS idx_generated_reports_brand_id ON generated_reports(brand_id);
CREATE INDEX IF NOT EXISTS idx_generated_reports_created_at ON generated_reports(created_at DESC);
