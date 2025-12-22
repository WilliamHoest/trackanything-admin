from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.schemas.brand import BrandCreate, BrandUpdate, BrandResponse
from app.security.auth import get_current_user
from app.core.config import settings
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD

router = APIRouter()

@router.get("/", response_model=List[dict])
async def get_brands(
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Get all brands for the current user"""
    brands = await crud.get_brands_by_profile(current_user.id)
    return brands

@router.get("/{brand_id}", response_model=dict)
async def get_brand(
    brand_id: int,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Get a specific brand with topics by ID"""
    brand = await crud.get_brand(brand_id)
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    # Check ownership
    if brand.get("profile_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    # Get topics for this brand
    topics = await crud.get_topics_by_brand(brand_id)
    brand["topics"] = topics
    
    return brand

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_brand(
    brand: BrandCreate,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Create a new brand"""
    new_brand = await crud.create_brand(brand, current_user.id)
    if not new_brand:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create brand"
        )
    return new_brand

@router.put("/{brand_id}", response_model=dict)
async def update_brand(
    brand_id: int,
    brand_update: BrandUpdate,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Update a brand"""
    updated_brand = await crud.update_brand(brand_id, brand_update, current_user.id)
    if not updated_brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    return updated_brand

@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand(
    brand_id: int,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Delete a brand"""
    success = await crud.delete_brand(brand_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )