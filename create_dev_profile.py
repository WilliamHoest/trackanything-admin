"""
Script to create a dev user profile in Supabase for development/testing
Run this once to set up the dev user profile
"""
import asyncio
from app.crud.supabase_crud import SupabaseCRUD
from app.core.supabase_client import get_supabase
from app.core.config import settings
import uuid

async def create_dev_profile():
    """Create profile for dev user"""

    # Dev user ID from dev_auth.py
    dev_user_id = "db186e82-e79c-45c8-bb4a-0261712e269c"
    dev_email = "madsrunge@hotmail.dk"

    print(f"Creating profile for dev user: {dev_email}")
    print(f"User ID: {dev_user_id}")

    # Get Supabase CRUD instance
    crud = SupabaseCRUD()

    try:
        # Check if profile already exists
        existing_profile = await crud.get_profile(uuid.UUID(dev_user_id))

        if existing_profile:
            print("✅ Profile already exists!")
            print(f"Profile: {existing_profile}")
            return

        # Create new profile with full user details
        profile_data = {
            "id": dev_user_id,
            "name": "Mads Runge",
            "email": dev_email,
            "phone_number": None,  # Optional
            "company_name": "Test Company",
            "contact_email": dev_email,
        }

        print(f"Creating profile with data: {profile_data}")

        # Use Supabase client directly to insert profile
        response = crud.supabase.table("profiles").insert(profile_data).execute()

        print("✅ Profile created successfully!")
        print(f"Response: {response.data}")

    except Exception as e:
        print(f"❌ Error creating profile: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 60)
    print("Dev User Profile Setup")
    print("=" * 60)
    asyncio.run(create_dev_profile())
