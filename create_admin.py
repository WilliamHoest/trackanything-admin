import asyncio
from app.core.supabase_client import get_supabase_admin
from app.crud.supabase_crud import supabase_crud
import uuid

async def create_first_admin():
    # --- CONFIGURATION ---
    EMAIL = "madsrunge@hotmail.dk"  # Update this if needed
    PASSWORD = "YourSecurePassword123"  # CHANGE THIS!
    NAME = "Mads Runge"
    COMPANY = "TrackAnything Admin"
    # ---------------------

    print(f"🚀 Bootstrapping Admin User: {EMAIL}")
    supabase_admin = get_supabase_admin()

    try:
        # 1. Create user in Supabase Auth
        print("Creating user in Supabase Auth...")
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

        # 2. Create Profile with 'admin' role
        print("Creating admin profile in database...")
        profile_data = {
            "id": str(user_id),
            "name": NAME,
            "email": EMAIL,
            "company_name": COMPANY,
            "role": "admin"
        }
        
        # Use direct insert to ensure role is set correctly (bypassing any defaults if necessary)
        response = supabase_admin.table("profiles").insert(profile_data).execute()
        
        print("✅ Admin profile created successfully!")
        print("-" * 40)
        print(f"Login Email: {EMAIL}")
        print(f"Login Pass: {PASSWORD}")
        print("-" * 40)
        print("You can now log in at http://localhost:3000/login")

    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(create_first_admin())
