
import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
load_dotenv()

# Get Supabase credentials
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("❌ Error: Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env file")
    sys.exit(1)

# Initialize Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

EMAIL = "madsrunge@hotmail.dk"
NEW_PASSWORD = "TrackAnything2024!"  # You can change this here if you want

def reset_password(email, new_password):
    print(f"🔒 Resetting password for {email}...")
    
    try:
        # Find user first
        users = supabase.auth.admin.list_users()
        user_id = None
        
        for user in users:
            if user.email and user.email.lower() == email.lower():
                user_id = user.id
                break
        
        if not user_id:
            print(f"❌ User with email {email} not found.")
            return

        print(f"✅ Found user ID: {user_id}")
        
        # Update user password
        response = supabase.auth.admin.update_user_by_id(
            user_id,
            {"password": new_password}
        )
        
        print(f"✅ Password successfully reset to: {new_password}")
        print("🚀 Login now: http://localhost:3000/login")
        
    except Exception as e:
        print(f"❌ Error resetting password: {e}")

if __name__ == "__main__":
    reset_password(EMAIL, NEW_PASSWORD)
