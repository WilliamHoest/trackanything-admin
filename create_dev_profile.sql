-- SQL script to create dev user profile in Supabase
-- Run this in Supabase SQL Editor (https://supabase.com/dashboard/project/YOUR_PROJECT/sql)

-- First, run the migration to add new columns (if not already done)
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS name TEXT,
ADD COLUMN IF NOT EXISTS email TEXT,
ADD COLUMN IF NOT EXISTS phone_number TEXT;

-- Insert or update dev user profile with full user details
INSERT INTO public.profiles (id, name, email, phone_number, company_name, contact_email)
VALUES (
    'db186e82-e79c-45c8-bb4a-0261712e269c',
    'Mads Runge',
    'madsrunge@hotmail.dk',
    NULL,  -- Add phone number if you want
    'Test Company',
    'madsrunge@hotmail.dk'
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    email = EXCLUDED.email,
    phone_number = EXCLUDED.phone_number,
    company_name = EXCLUDED.company_name,
    contact_email = EXCLUDED.contact_email;

-- Verify the profile was created
SELECT * FROM public.profiles WHERE id = 'db186e82-e79c-45c8-bb4a-0261712e269c';
