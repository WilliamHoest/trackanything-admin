from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.schemas.keyword import KeywordCreate, KeywordUpdate
from app.security.auth import get_current_user
from app.security.dev_auth import get_dev_user
from app.core.config import settings
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD

# Use development auth in debug mode, real auth in production
get_user = get_dev_user if settings.debug else get_current_user

router = APIRouter()

@router.get("/topics/{topic_id}/keywords", response_model=List[dict])
async def get_keywords_by_topic(
    topic_id: int,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_user)
):
    """Get all keywords for a specific topic"""
    # Check topic ownership
    topic = await crud.get_topic(topic_id)
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    # Check brand ownership
    brand = await crud.get_brand(topic["brand_id"])
    if not brand or brand.get("profile_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    keywords = await crud.get_keywords_by_topic(topic_id)
    return keywords

@router.post("/topics/{topic_id}/keywords", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_keyword(
    topic_id: int,
    keyword: KeywordCreate,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_user)
):
    """Create a new keyword for a topic"""
    # Check topic ownership
    topic = await crud.get_topic(topic_id)
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    # Check brand ownership
    brand = await crud.get_brand(topic["brand_id"])
    if not brand or brand.get("profile_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    new_keyword = await crud.create_keyword(keyword, topic_id)
    if not new_keyword:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create keyword"
        )
    return new_keyword

@router.delete("/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_keyword(
    keyword_id: int,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_user)
):
    """Delete a keyword"""
    # Get keyword and check ownership through topic->brand chain
    keyword = await crud.get_keyword(keyword_id)
    if not keyword:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keyword not found"
        )
    
    # Check topic ownership
    topic = await crud.get_topic(keyword["topic_id"])
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keyword not found"
        )
    
    # Check brand ownership
    brand = await crud.get_brand(topic["brand_id"])
    if not brand or brand.get("profile_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keyword not found"
        )
    
    success = await crud.delete_keyword(keyword_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete keyword"
        )