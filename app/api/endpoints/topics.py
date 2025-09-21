from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.schemas.topic import TopicCreate, TopicUpdate, TopicResponse, TopicWithKeywords
from app.schemas.brand import BrandResponse
from app.security.auth import get_current_user
from app.security.dev_auth import get_dev_user
from app.core.database import get_db
from app.core.config import settings
from app.crud import crud

# Use development auth in debug mode, real auth in production
get_user = get_dev_user if settings.debug else get_current_user

router = APIRouter()

@router.get("/brands/{brand_id}/topics", response_model=List[TopicWithKeywords])
def get_topics_by_brand(
    brand_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """Get all topics for a specific brand"""
    # Check if brand belongs to current user
    brand = crud.get_brand(db, brand_id)
    if not brand or brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    topics = crud.get_topics_by_brand(db, brand_id)
    return topics

@router.get("/{topic_id}", response_model=TopicWithKeywords)
def get_topic(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """Get a specific topic by ID"""
    topic = crud.get_topic(db, topic_id)
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    # Check if topic belongs to current user (through brand)
    if topic.brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    return topic

@router.post("/brands/{brand_id}/topics", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
def create_topic_for_brand(
    brand_id: int,
    topic: TopicCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """Create a new topic for a specific brand"""
    # Check if brand belongs to current user
    brand = crud.get_brand(db, brand_id)
    if not brand or brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    return crud.create_topic(db=db, topic=topic, brand_id=brand_id)

@router.put("/{topic_id}", response_model=TopicResponse)
def update_topic(
    topic_id: int,
    topic: TopicUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """Update a topic"""
    # Check if topic exists and belongs to current user
    db_topic = crud.get_topic(db, topic_id)
    if not db_topic or db_topic.brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    updated_topic = crud.update_topic(db=db, topic_id=topic_id, topic=topic)
    if not updated_topic:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update topic"
        )
    
    return updated_topic

@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """Delete a topic"""
    # Check if topic exists and belongs to current user
    db_topic = crud.get_topic(db, topic_id)
    if not db_topic or db_topic.brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    success = crud.delete_topic(db=db, topic_id=topic_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete topic"
        )