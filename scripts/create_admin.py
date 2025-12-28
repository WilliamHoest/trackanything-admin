import sys
import os
import asyncio
import uuid

# Add parent directory to path to allow importing app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase_admin
from app.crud.supabase_crud import supabase_crud

async def create_first_admin():
    # --- CONFIGURATION ---
    EMAIL = "Williamhoest@gmail.com"  # Update this if needed
    PASSWORD = "Høst1234"  # CHANGE THIS!
    NAME = "William Høst"
    COMPANY = "TrackAnything Admin"
    # ---------------------

    print(f"🚀 Bootstrapping Admin User: {EMAIL}")
    supabase_admin = get_supabase_admin()

    try:
        # 1. Create user in Supabase Auth
        print("Creating user in Supabase Auth...")
        try:
            auth_response = supabase_admin.auth.admin.create_user({
                "email": EMAIL,
                "password": PASSWORD,
                "email_confirm": True,
                "user_metadata": {
                    "name": NAME,
                    "company_name": COMPANY
                }
            })
            
            # Determine the user ID from response
            if hasattr(auth_response, 'user') and auth_response.user:
                auth_user = auth_response.user
            elif hasattr(auth_response, 'data') and auth_response.data and hasattr(auth_response.data, 'user'):
                auth_user = auth_response.data.user
            else:
                auth_user = auth_response
                
            user_id = uuid.UUID(auth_user.id)
            print(f"✅ Auth user created with ID: {user_id}")

        except Exception as auth_error:
            # If user already exists in Auth, try to find them
            print(f"⚠️  Auth user creation failed (maybe exists?): {auth_error}")
            print("🔍 Looking up existing user...")
            
            users = supabase_admin.auth.admin.list_users()
            target_user = None
            for user in users:
                if user.email and user.email.lower() == EMAIL.lower():
                    target_user = user
                    break
            
            if not target_user:
                print("❌ Could not find or create user.")
                return

            user_id = uuid.UUID(target_user.id)
            print(f"✅ Found existing User ID: {user_id}")


        # 2. Create or Update Profile with 'admin' role
        print("Creating/Updating admin profile in database...")
        profile_data = {
            "id": str(user_id),
            "name": NAME,
            "email": EMAIL,
            "company_name": COMPANY,
            "role": "admin"
        }
        
        # Use upsert to handle both creation and update scenarios
        # This fixes the "duplicate key" error if a trigger auto-created the profile
        response = supabase_admin.table("profiles").upsert(profile_data).execute()
        
        print("✅ Admin profile created/updated successfully!")
        print("-" * 40)
        print(f"Login Email: {EMAIL}")
        print(f"Login Pass: {PASSWORD}")
        print("-" * 40)
        print("You can now log in at http://localhost:3000/login")

    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(create_first_admin())