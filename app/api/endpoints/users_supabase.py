from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.profile import ProfileCreate, ProfileUpdate, ProfileResponse
from app.security.auth import get_current_user
from app.security.dev_auth import get_dev_user
from app.core.config import settings
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD

# Use development auth in debug mode, real auth in production
get_user = get_dev_user if settings.debug else get_current_user

router = APIRouter()

@router.get("/profile", response_model=dict)
async def get_current_user_profile(
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_user)
):
    """Get current user's profile"""
    profile = await crud.get_profile(current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    return profile

@router.post("/profile", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_user_profile(
    profile: ProfileCreate,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_user)
):
    """Create user profile"""
    new_profile = await crud.create_profile(profile, current_user.id)
    if not new_profile:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create profile"
        )
    return new_profile

@router.put("/profile", response_model=dict)
async def update_user_profile(
    profile_update: ProfileUpdate,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_user)
):
    """Update current user's profile"""
    updated_profile = await crud.update_profile(current_user.id, profile_update)
    if not updated_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    return updated_profile