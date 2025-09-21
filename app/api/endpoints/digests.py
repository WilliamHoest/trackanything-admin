from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, Any
from app.security.auth import get_current_user
from app.security.dev_auth import get_dev_user
from app.core.database import get_db
from app.core.config import settings
from app.crud import crud
from app.services.digest_service import create_and_send_digest

# Use development auth in debug mode, real auth in production
get_user = get_dev_user if settings.debug else get_current_user

router = APIRouter()

class DigestResponse(BaseModel):
    success: bool
    message: str
    mentions_sent: int
    mentions_updated: int = 0
    webhook_url: str = ""

@router.post("/send/{brand_id}", response_model=DigestResponse)
def send_digest(
    brand_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Send digest of new mentions for a specific brand to its webhook
    
    Args:
        brand_id: ID of the brand to send digest for
        
    Returns:
        DigestResponse with result information
    """
    
    # Verify brand exists and belongs to current user
    brand = crud.get_brand(db, brand_id)
    if not brand or brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    try:
        # Create and send the digest
        result = create_and_send_digest(db, brand_id)
        
        return DigestResponse(
            success=result["success"],
            message=result["message"],
            mentions_sent=result["mentions_sent"],
            mentions_updated=result.get("mentions_updated", 0),
            webhook_url=result.get("webhook_url", "")
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error sending digest: {str(e)}"
        )

@router.get("/preview/{brand_id}")
def preview_digest(
    brand_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Preview digest content without sending it
    
    Args:
        brand_id: ID of the brand to preview digest for
        
    Returns:
        Preview of digest content
    """
    
    # Verify brand exists and belongs to current user
    brand = crud.get_brand(db, brand_id)
    if not brand or brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    # Get all unsent mentions for this brand
    unsent_mentions = crud.get_unsent_mentions_by_brand(db, brand_id)
    
    if not unsent_mentions:
        return {
            "brand_name": brand.name,
            "total_mentions": 0,
            "message": "No new mentions to send",
            "mentions_by_topic": {}
        }
    
    # Group mentions by topic for preview
    mentions_by_topic = {}
    for mention in unsent_mentions:
        topic_name = mention.topic.name if mention.topic else "Uncategorized"
        if topic_name not in mentions_by_topic:
            mentions_by_topic[topic_name] = []
        
        mentions_by_topic[topic_name].append({
            "id": mention.id,
            "caption": mention.caption,
            "post_link": mention.post_link,
            "platform": mention.platform.name if mention.platform else "Unknown",
            "published_at": mention.published_at.isoformat() if mention.published_at else None
        })
    
    return {
        "brand_name": brand.name,
        "total_mentions": len(unsent_mentions),
        "message": f"Preview of {len(unsent_mentions)} mentions ready to send",
        "mentions_by_topic": mentions_by_topic
    }