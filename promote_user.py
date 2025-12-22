import asyncio
from app.core.supabase_client import get_supabase_admin
import sys

async def promote_user(email: str):
    print(f"🚀 Promoting user {email} to admin...")
    supabase_admin = get_supabase_admin()

    try:
        # Update the profile role to 'admin'
        result = supabase_admin.table("profiles").update({"role": "admin"}).eq("email", email).execute()
        
        if result.data:
            print(f"✅ Successfully promoted {email} to admin!")
        else:
            print(f"❌ User with email {email} not found in profiles table.")

    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python promote_user.py your-email@example.com")
    else:
        asyncio.run(promote_user(sys.argv[1]))
