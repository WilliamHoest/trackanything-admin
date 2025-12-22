-- Add role column to profiles
ALTER TABLE profiles 
ADD COLUMN IF NOT EXISTS role text CHECK (role IN ('admin', 'customer')) DEFAULT 'customer';

-- Function to check if the current user is an admin
CREATE OR REPLACE FUNCTION public.is_admin() 
RETURNS boolean AS $$
DECLARE
  current_role text;
BEGIN
  SELECT role INTO current_role FROM public.profiles WHERE id = auth.uid();
  RETURN current_role = 'admin';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RLS Policies

-- PROFILES
-- Drop existing policies if they conflict or are too restrictive? 
-- Assuming additive policies for Admin.

CREATE POLICY "Admins can do everything on profiles" 
ON profiles 
FOR ALL 
TO authenticated
USING (public.is_admin());

-- BRANDS
CREATE POLICY "Admins can do everything on brands" 
ON brands 
FOR ALL 
TO authenticated
USING (public.is_admin());

-- TOPICS
CREATE POLICY "Admins can do everything on topics" 
ON topics 
FOR ALL 
TO authenticated
USING (public.is_admin());

-- KEYWORDS
CREATE POLICY "Admins can do everything on keywords" 
ON keywords 
FOR ALL 
TO authenticated
USING (public.is_admin());

-- MENTIONS
CREATE POLICY "Admins can do everything on mentions" 
ON mentions 
FOR ALL 
TO authenticated
USING (public.is_admin());
