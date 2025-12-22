from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.schemas.topic import TopicCreate, TopicUpdate
from app.security.auth import get_current_user
from app.core.config import settings
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD

router = APIRouter()

@router.get("/brands/{brand_id}/topics", response_model=List[dict])
async def get_topics_by_brand(
    brand_id: int,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Get all topics for a specific brand"""
    # Check if brand belongs to current user
    brand = await crud.get_brand(brand_id)
    if not brand or brand.get("profile_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    topics = await crud.get_topics_by_brand(brand_id)
    return topics

@router.get("/{topic_id}", response_model=dict)
async def get_topic(
    topic_id: int,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Get a specific topic with keywords"""
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
    
    return topic

@router.post("/brands/{brand_id}/topics", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_topic(
    brand_id: int,
    topic: TopicCreate,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Create a new topic for a brand"""
    # Check if brand belongs to current user
    brand = await crud.get_brand(brand_id)
    if not brand or brand.get("profile_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    new_topic = await crud.create_topic(topic, brand_id)
    if not new_topic:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create topic"
        )
    return new_topic

@router.put("/{topic_id}", response_model=dict)
async def update_topic(
    topic_id: int,
    topic_update: TopicUpdate,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Update a topic"""
    # Get existing topic and check ownership
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
    
    # Update topic in Supabase
    updated_topic = await crud.update_topic(topic_id, topic_update)
    if not updated_topic:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update topic"
        )
    
    return updated_topic

@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(
    topic_id: int,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Delete a topic"""
    # Get existing topic and check ownership
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
    
    success = await crud.delete_topic(topic_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete topic"
        )