-- Migration: Update profiles table to be more user-friendly
-- Adds standard user profile fields: name, email, phone_number
-- Makes company_name optional

-- Add new columns to profiles table
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS name TEXT,
ADD COLUMN IF NOT EXISTS email TEXT,
ADD COLUMN IF NOT EXISTS phone_number TEXT;

-- Rename contact_email to keep it as fallback (or we can drop it)
-- For now, let's keep contact_email for backwards compatibility
-- but email will be the primary field

-- Add NOT NULL constraint to essential fields (after data migration if needed)
-- We'll keep them nullable for now to allow gradual migration

-- Update the dev user profile with proper data
UPDATE public.profiles
SET
    name = 'Mads Runge',
    email = 'madsrunge@hotmail.dk',
    company_name = 'Test Company'
WHERE id = 'db186e82-e79c-45c8-bb4a-0261712e269c';

-- Verify the update
SELECT * FROM public.profiles WHERE id = 'db186e82-e79c-45c8-bb4a-0261712e269c';
