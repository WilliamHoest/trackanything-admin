from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from app.security.auth import get_current_user
from app.core.config import settings
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD

router = APIRouter()

@router.get("/", response_model=List[dict])
async def get_mentions(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    brand_id: Optional[int] = Query(None, description="Filter by brand ID"),
    topic_id: Optional[int] = Query(None, description="Filter by topic ID"), 
    platform_id: Optional[int] = Query(None, description="Filter by platform ID"),
    read_status: Optional[bool] = Query(None, description="Filter by read status"),
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """
    Get mentions with optional filtering using Supabase REST API.
    Returns mentions for brands owned by the current user.
    """
    # Get mentions using Supabase REST API
    mentions = await crud.get_mentions_by_profile(
        profile_id=current_user.id,
        skip=skip,
        limit=limit,
        brand_id=brand_id,
        platform_id=platform_id,
        read_status=read_status
    )
    
    return mentions

@router.patch("/{mention_id}/read")
async def mark_mention_as_read(
    mention_id: int,
    read_status: bool = True,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """
    Mark a mention as read or unread using Supabase REST API.
    """
    result = await crud.update_mention_read_status(mention_id, read_status)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mention not found"
        )
    
    return result