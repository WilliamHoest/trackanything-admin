import sys
import os
import asyncio

# Add parent directory to path to allow importing app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase_admin

async def full_reset_user(email: str):
    print(f"🗑️  Attempting to fully delete user: {email}")
    supabase_admin = get_supabase_admin()

    try:
        # 1. Find the user ID in Auth system (The "Passport")
        print("🔍 Searching for user in Auth system...")
        auth_users = supabase_admin.auth.admin.list_users()
        
        target_user = None
        for user in auth_users:
            if user.email and user.email.lower() == email.lower():
                target_user = user
                break
        
        if not target_user:
            print(f"⚠️  User {email} not found in Auth system.")
            return

        user_id = target_user.id
        print(f"✅ Found Auth User ID: {user_id}")

        # 2. Delete from Auth system
        print("🔥 Deleting from Auth system...")
        supabase_admin.auth.admin.delete_user(user_id)
        print("✅ Auth user deleted.")

        # 3. Delete from Profiles (The "CV") - just in case
        print("🧹 Cleaning up public.profiles table...")
        supabase_admin.table("profiles").delete().eq("id", user_id).execute()
        print("✅ Profile cleaned up.")

        print("-" * 40)
        print("🎉 User fully wiped.")

    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    EMAIL = "madsrunge@hotmail.dk"  # Default email
    if len(sys.argv) > 1:
        EMAIL = sys.argv[1]
    
    asyncio.run(full_reset_user(EMAIL))
