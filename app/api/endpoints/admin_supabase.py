from fastapi import APIRouter, Depends, HTTPException, status, Response
from typing import List
from app.security.auth import get_current_admin
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.core.supabase_client import get_supabase_admin
from app.crud.supabase_crud import supabase_crud
from app.schemas.profile import ProfileCreate, ProfileUpdate, ProfileResponse
import uuid

router = APIRouter()

@router.get("/users", response_model=List[ProfileResponse])
async def get_users(
    skip: int = 0,
    limit: int = 100,
    current_admin = Depends(get_current_admin)
):
    """
    List all users (profiles).
    """
    supabase_admin = get_supabase_admin()
    result = supabase_admin.table("profiles").select("*").range(skip, skip + limit - 1).execute()
    return result.data or []

@router.post("/users", response_model=UserResponse)
async def create_user(
    user_in: UserCreate,
    current_admin = Depends(get_current_admin)
):
    """
    Create a new user (admin only).
    Creates user in Supabase Auth and then ensures a Profile exists with the correct role.
    """
    supabase_admin = get_supabase_admin()
    
    # 1. Create user in Supabase Auth
    try:
        # admin.create_user is the method for server-side user creation
        # It auto-confirms the email usually.
        auth_response = supabase_admin.auth.admin.create_user({
            "email": user_in.email,
            "password": user_in.password,
            "email_confirm": True,
            "user_metadata": {
                "name": user_in.name,
                "company_name": user_in.company_name
            }
        })
        
        # Check if auth_response has user
        if hasattr(auth_response, 'user') and auth_response.user:
            auth_user = auth_response.user
        elif hasattr(auth_response, 'data') and auth_response.data and hasattr(auth_response.data, 'user'):
             auth_user = auth_response.data.user
        else:
             # Fallback for some library versions
             auth_user = auth_response
        
        if not auth_user or not hasattr(auth_user, 'id'):
             raise HTTPException(status_code=400, detail="Failed to create user in Auth - No ID returned")
             
        user_id = uuid.UUID(auth_user.id)
        
    except Exception as e:
        print(f"Auth creation failed: {e}")
        raise HTTPException(status_code=400, detail=f"Auth creation failed: {str(e)}")

    # 2. Create or Update profile in 'profiles' table with role
    try:
        # Check if profile exists (maybe created by trigger)
        existing_profile = await supabase_crud.get_profile(user_id)
        
        if existing_profile:
            # Update role and details
            profile_update = ProfileUpdate(
                name=user_in.name,
                company_name=user_in.company_name,
                role=user_in.role
            )
            profile = await supabase_crud.update_profile(user_id, profile_update)
        else:
            # Create profile
            profile_create = ProfileCreate(
                name=user_in.name,
                email=user_in.email,
                company_name=user_in.company_name,
                role=user_in.role
            )
            profile = await supabase_crud.create_profile(profile_create, user_id)
            
        if not profile:
             raise HTTPException(status_code=500, detail="Failed to create/update profile")
             
        return UserResponse(
            id=user_id,
            email=user_in.email,
            role=profile.get("role", "customer"),
            name=user_in.name,
            company_name=profile.get("company_name")
        )
        
    except Exception as e:
        print(f"Profile creation failed: {e}")
        # Cleanup auth user if profile fails? 
        # For now, let's just fail.
        raise HTTPException(status_code=500, detail=f"Profile creation failed: {str(e)}")

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    user_in: UserUpdate,
    current_admin = Depends(get_current_admin)
):
    """
    Update a user's details (Auth and Profile).
    """
    supabase_admin = get_supabase_admin()
    
    # 1. Update Auth (if email/password/metadata changed)
    auth_attrs = {}
    if user_in.email:
        auth_attrs["email"] = user_in.email
    if user_in.password:
        auth_attrs["password"] = user_in.password
    
    user_metadata = {}
    if user_in.name:
        user_metadata["name"] = user_in.name
    if user_in.company_name:
        user_metadata["company_name"] = user_in.company_name
        
    if user_metadata:
        auth_attrs["user_metadata"] = user_metadata
        
    if auth_attrs:
        try:
            supabase_admin.auth.admin.update_user_by_id(str(user_id), auth_attrs)
        except Exception as e:
            print(f"Auth update failed: {e}")
            raise HTTPException(status_code=400, detail=f"Auth update failed: {str(e)}")

    # 2. Update Profile
    try:
        profile_update = ProfileUpdate(
            name=user_in.name,
            company_name=user_in.company_name,
            email=user_in.email, # Sync email to profile
            role=user_in.role
        )
        profile = await supabase_crud.update_profile(user_id, profile_update)
        
        if not profile:
             raise HTTPException(status_code=404, detail="Profile not found or update failed")
             
        return UserResponse(
            id=user_id,
            email=user_in.email or profile.get("email"),
            role=profile.get("role", "customer"),
            name=profile.get("name"),
            company_name=profile.get("company_name")
        )
        
    except Exception as e:
        print(f"Profile update failed: {e}")
        raise HTTPException(status_code=500, detail=f"Profile update failed: {str(e)}")

@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    current_admin = Depends(get_current_admin)
):
    """
    Delete a user (Auth and Profile).
    """
    supabase_admin = get_supabase_admin()
    
    try:
        # Delete from Auth - this usually cascades to profile if set up, 
        # but we also explicitly check/delete profile for safety if needed.
        # However, supabase_crud doesn't have delete_profile exposed generally.
        # Auth deletion is the primary source of truth.
        
        supabase_admin.auth.admin.delete_user(str(user_id))
        
        # Optionally cleanup profile if cascade didn't work (requires implementing delete_profile)
        # For now assuming cascade or manual cleanup not strictly required if Auth is gone.
        
        return Response(status_code=status.HTTP_204_NO_CONTENT)
        
    except Exception as e:
        print(f"User deletion failed: {e}")
        raise HTTPException(status_code=500, detail=f"User deletion failed: {str(e)}")

