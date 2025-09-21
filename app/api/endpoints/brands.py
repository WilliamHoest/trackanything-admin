from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.schemas.brand import BrandCreate, BrandUpdate, BrandResponse, BrandWithTopics
from app.security.auth import get_current_user
from app.security.dev_auth import get_dev_user
from app.core.database import get_db
from app.core.config import settings
from app.crud import crud

# Use development auth in debug mode, real auth in production
get_user = get_dev_user if settings.debug else get_current_user

router = APIRouter()

@router.get("/", response_model=List[BrandResponse])
def get_brands(
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """Get all brands for the current user"""
    brands = crud.get_brands_by_profile(db, current_user.id)
    return brands

@router.get("/{brand_id}", response_model=BrandWithTopics)
def get_brand(
    brand_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """Get a specific brand by ID with its topics"""
    brand = crud.get_brand(db, brand_id)
    if not brand or brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    return brand

@router.post("/", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
def create_brand(
    brand: BrandCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """Create a new brand"""
    return crud.create_brand(db=db, brand=brand, profile_id=current_user.id)

@router.put("/{brand_id}", response_model=BrandResponse)
def update_brand(
    brand_id: int,
    brand: BrandUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """Update a brand"""
    # Check if brand belongs to current user
    db_brand = crud.get_brand(db, brand_id)
    if not db_brand or db_brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    updated_brand = crud.update_brand(db=db, brand_id=brand_id, brand=brand)
    if not updated_brand:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update brand"
        )
    
    return updated_brand

@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_brand(
    brand_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """Delete a brand"""
    # Check if brand belongs to current user
    db_brand = crud.get_brand(db, brand_id)
    if not db_brand or db_brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    success = crud.delete_brand(db=db, brand_id=brand_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete brand"
        )