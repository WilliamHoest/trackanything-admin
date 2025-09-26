from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from app.security.auth import get_current_user
from app.security.dev_auth import get_dev_user
from app.core.database import get_db
from app.core.config import settings
from app.crud import crud
from app.schemas.mention import MentionCreate, MentionUpdate, MentionResponse
from app.models import models

# Use development auth in debug mode, real auth in production
get_user = get_dev_user if settings.debug else get_current_user

router = APIRouter()

@router.get("/", response_model=List[MentionResponse])
def get_mentions(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    brand_id: Optional[int] = Query(None, description="Filter by brand ID"),
    topic_id: Optional[int] = Query(None, description="Filter by topic ID"), 
    platform_id: Optional[int] = Query(None, description="Filter by platform ID"),
    read_status: Optional[bool] = Query(None, description="Filter by read status"),
    notified_status: Optional[bool] = Query(None, description="Filter by notification status"),
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Get mentions with optional filtering.
    Returns mentions for brands owned by the current user.
    """
    # Get user's brands for filtering
    user_brands = crud.get_brands_by_profile(db, current_user.id)
    user_brand_ids = [brand.id for brand in user_brands]
    
    if not user_brand_ids:
        return []
    
    # Apply brand filter if specified
    if brand_id is not None:
        if brand_id not in user_brand_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Brand not found"
            )
        user_brand_ids = [brand_id]
    
    # Build query
    query = db.query(models.Mention).options(
        joinedload(models.Mention.platform),
        joinedload(models.Mention.brand), 
        joinedload(models.Mention.topic)
    ).filter(models.Mention.brand_id.in_(user_brand_ids))
    
    # Apply filters
    if topic_id is not None:
        query = query.filter(models.Mention.topic_id == topic_id)
    if platform_id is not None:
        query = query.filter(models.Mention.platform_id == platform_id)
    if read_status is not None:
        query = query.filter(models.Mention.read_status == read_status)
    if notified_status is not None:
        query = query.filter(models.Mention.notified_status == notified_status)
    
    # Apply pagination and ordering
    mentions = query.order_by(models.Mention.published_at.desc()).offset(skip).limit(limit).all()
    
    return mentions

@router.get("/{mention_id}", response_model=MentionResponse)
def get_mention(
    mention_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Get a specific mention by ID.
    Only returns mentions for brands owned by the current user.
    """
    mention = crud.get_mention(db, mention_id)
    if not mention:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mention not found"
        )
    
    # Check if user owns the brand this mention belongs to
    brand = crud.get_brand(db, mention.brand_id)
    if not brand or brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mention not found"
        )
    
    return mention

@router.post("/", response_model=MentionResponse, status_code=status.HTTP_201_CREATED)
def create_mention(
    mention: MentionCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Create a new mention.
    Brand must be owned by the current user.
    """
    # Verify brand ownership
    brand = crud.get_brand(db, mention.brand_id)
    if not brand or brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    # Verify topic belongs to brand
    topic = crud.get_topic(db, mention.topic_id)
    if not topic or topic.brand_id != mention.brand_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found or doesn't belong to the specified brand"
        )
    
    # Verify platform exists
    platform = crud.get_platform(db, mention.platform_id)
    if not platform:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform not found"
        )
    
    return crud.create_mention(db, mention)

@router.put("/{mention_id}", response_model=MentionResponse)
def update_mention(
    mention_id: int,
    mention_update: MentionUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Update a mention.
    Only mentions for brands owned by the current user can be updated.
    """
    # Get existing mention
    existing_mention = crud.get_mention(db, mention_id)
    if not existing_mention:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mention not found"
        )
    
    # Check brand ownership
    brand = crud.get_brand(db, existing_mention.brand_id)
    if not brand or brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mention not found"
        )
    
    # Validate brand_id if provided
    if mention_update.brand_id is not None:
        new_brand = crud.get_brand(db, mention_update.brand_id)
        if not new_brand or new_brand.profile_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Brand not found"
            )
    
    # Validate topic_id if provided
    if mention_update.topic_id is not None:
        topic = crud.get_topic(db, mention_update.topic_id)
        target_brand_id = mention_update.brand_id or existing_mention.brand_id
        if not topic or topic.brand_id != target_brand_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Topic not found or doesn't belong to the specified brand"
            )
    
    # Validate platform_id if provided
    if mention_update.platform_id is not None:
        platform = crud.get_platform(db, mention_update.platform_id)
        if not platform:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Platform not found"
            )
    
    updated_mention = crud.update_mention(db, mention_id, mention_update)
    if not updated_mention:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update mention"
        )
    
    return updated_mention

@router.delete("/{mention_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mention(
    mention_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Delete a mention.
    Only mentions for brands owned by the current user can be deleted.
    """
    # Get existing mention
    mention = crud.get_mention(db, mention_id)
    if not mention:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mention not found"
        )
    
    # Check brand ownership
    brand = crud.get_brand(db, mention.brand_id)
    if not brand or brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mention not found"
        )
    
    success = crud.delete_mention(db, mention_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete mention"
        )

@router.patch("/{mention_id}/read", response_model=MentionResponse)
def mark_mention_as_read(
    mention_id: int,
    read_status: bool = True,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Mark a mention as read or unread.
    Convenience endpoint for updating read status.
    """
    mention_update = MentionUpdate(read_status=read_status)
    return update_mention(mention_id, mention_update, db, current_user)

@router.patch("/{mention_id}/notify", response_model=MentionResponse)
def mark_mention_as_notified(
    mention_id: int,
    notified_status: bool = True,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Mark a mention as notified or not notified.
    Convenience endpoint for updating notification status.
    """
    mention_update = MentionUpdate(notified_status=notified_status)
    return update_mention(mention_id, mention_update, db, current_user)